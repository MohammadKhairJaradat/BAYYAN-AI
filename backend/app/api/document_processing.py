import mimetypes
import math
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.auth.tier_limits import normalize_tier
from app.auth.usage import reserve_usage, settle_usage
from app.extraction import extract_document
from app.extraction.base import DeductionCategory as ExtractionDeductionCategory, DocumentType
from app.models import User
from app.models.connection import get_db
from app.models.database import Deduction, Document, TaxProfile
from app.models.schemas import DeductionRead, DocumentProcessingResult, ExtractionDebugResult
from app.api.documents import MAX_FILE_SIZE, PREVIEW_MIME, _extension
from app.services.file_validation import matches_image_or_pdf
from app.services.storage import StorageService, get_storage

router = APIRouter(prefix="/documents", tags=["document_processing"])


def _guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


@router.post("/{document_id}/process", response_model=DocumentProcessingResult)
async def process_document(
    document_id: uuid.UUID,
    tax_profile_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    doc = await db.get(Document, document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if tax_profile_id is not None:
        profile = await db.get(TaxProfile, tax_profile_id)
        if profile is None or profile.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Tax profile not found")

    file_bytes = await storage.download_file(doc.file_path)
    ext = _extension(doc.original_filename)
    if (
        len(file_bytes) > MAX_FILE_SIZE
        or ext not in PREVIEW_MIME
        or not matches_image_or_pdf(file_bytes, ext)
    ):
        raise HTTPException(status_code=400, detail="Stored document has an invalid or oversized file type")
    mime_type = _guess_mime(doc.original_filename)

    reservation_id = await reserve_usage(
        db, user_id=current_user.id, tier=normalize_tier(current_user.subscription_tier),
        operation="extraction", idempotency_key=idempotency_key,
    )
    try:
        result = await extract_document(file_bytes, mime_type=mime_type)
    finally:
        await settle_usage(db, reservation_id)

    if (result.amount is not None and not math.isfinite(result.amount)) or not math.isfinite(result.confidence):
        result.amount = None
        result.confidence = 0.0
        result.error = "Extractor returned an invalid numeric value"

    extracted_data = result.to_jsonb()
    # A weak extraction is saved for review, but must not change tax inputs.
    extracted_data["needs_review"] = result.confidence < 0.85 or result.error is not None

    # Serialize concurrent requests only during the database write. Extraction
    # runs before the lock so a slow provider does not hold a row lock.
    doc = (await db.execute(
        select(Document).where(Document.id == document_id).with_for_update()
    )).scalar_one()

    # Hybrid Classification Relabeling: trust the extractor if it is highly confident that the user mislabeled it.
    RELABEL_CONFIDENCE_THRESHOLD = 0.85
    if (
        result.document_type != DocumentType.UNKNOWN
        and result.document_type.value != doc.document_type
        and result.confidence >= RELABEL_CONFIDENCE_THRESHOLD
    ):
        extracted_data["user_type_corrected_from"] = doc.document_type
        doc.document_type = result.document_type.value

    if result.error:
        doc.processing_status = "failed"
    else:
        doc.processing_status = "processed"

    # Extraction proposes values; only an explicit deduction request may change
    # the taxpayer's profile. Preserve a previously linked deduction on retry.
    existing = (await db.execute(
        select(Deduction).where(Deduction.document_id == doc.id)
    )).scalar_one_or_none()
    extracted_data["awaiting_confirmation"] = (
        existing is None
        and result.is_usable
        and result.category != ExtractionDeductionCategory.UNKNOWN
    )
    doc.extracted_data = extracted_data
    deduction_id = existing.id if existing is not None else None

    await db.commit()
    await db.refresh(doc)

    return DocumentProcessingResult(
        document_id=doc.id,
        processing_status=doc.processing_status,
        extracted_data=doc.extracted_data,
        deduction_id=deduction_id,
    )


@router.get("/{document_id}/extraction-debug", response_model=ExtractionDebugResult)
async def extraction_debug(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return extraction fields and any deduction the taxpayer linked explicitly."""
    doc = await db.get(Document, document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    stmt = select(Deduction).where(Deduction.document_id == doc.id)
    deduction_row = (await db.execute(stmt)).scalar_one_or_none()

    return ExtractionDebugResult(
        document_id=doc.id,
        original_filename=doc.original_filename,
        document_type=doc.document_type,
        processing_status=doc.processing_status,
        upload_date=doc.upload_date,
        extracted_data=doc.extracted_data,
        deduction=DeductionRead.model_validate(deduction_row) if deduction_row else None,
    )
