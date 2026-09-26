import io
import logging
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.auth.tier_limits import get_tier_limits, normalize_tier
from app.auth.usage import get_monthly_usage, release_usage, reserve_usage, settle_usage
from app.models.connection import get_db
from app.models.database import Deduction, Document, TaxProfile, User
from app.models.schemas import DocumentRead
from app.services.storage import StorageService, get_storage
from app.services.file_validation import matches_image_or_pdf

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE = 1 << 20  # 1 MB
PREVIEW_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
}


def _extension(filename: str | None) -> str:
    if not filename:
        return ""
    return PurePosixPath(filename).suffix.lstrip(".").lower()


@router.post("/upload", response_model=DocumentRead, status_code=201)
async def upload_document(
    file: UploadFile,
    document_type: str = Form(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    ext = _extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    tier = normalize_tier(current_user.subscription_tier)
    limits = get_tier_limits(tier)
    usage = await get_monthly_usage(db, current_user.id)
    docs_used = usage.doc_count if usage else 0
    if docs_used >= limits.max_docs_per_month:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly document upload quota reached for your {tier} plan "
                f"({limits.max_docs_per_month}/month)."
            ),
        )

    buffer = bytearray()
    while chunk := await file.read(CHUNK_SIZE):
        buffer.extend(chunk)
        if len(buffer) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {MAX_FILE_SIZE} bytes",
            )

    if not matches_image_or_pdf(buffer, ext) or file.content_type != PREVIEW_MIME[ext]:
        raise HTTPException(status_code=400, detail="File contents do not match its image/PDF type")

    reservation_id = await reserve_usage(
        db, user_id=current_user.id, tier=tier, operation="document_upload",
        idempotency_key=idempotency_key,
    )
    original_filename = file.filename or "unknown"
    object_key = None
    try:
        object_key = await storage.upload_file(bytes(buffer), original_filename, current_user.id)
        doc = Document(
            user_id=current_user.id,
            file_path=object_key,
            original_filename=original_filename,
            document_type=document_type,
            processing_status="pending",
        )
        db.add(doc)
        await db.commit()
    except Exception:
        await db.rollback()
        if object_key is not None:
            try:
                await storage.delete_file(object_key)
            except Exception:
                logger.exception("Failed to clean up an uncommitted document object")
        await release_usage(db, reservation_id)
        raise
    await settle_usage(db, reservation_id)
    await db.refresh(doc)
    return doc


@router.get("/", response_model=list[DocumentRead])
async def list_documents(
    document_type: str | None = None,
    processing_status: str | None = None,
    category: str | None = None,
    year: int | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).where(Document.user_id == current_user.id)
    if document_type:
        stmt = stmt.where(Document.document_type == document_type)
    if processing_status:
        stmt = stmt.where(Document.processing_status == processing_status)
    if category:
        stmt = stmt.where(Document.extracted_data["category"].astext == category)
    if year:
        stmt = stmt.where(extract("year", Document.upload_date) == year)
    result = await db.execute(stmt)
    docs = result.scalars().all()

    # Bulk ownership-scoped query for linked document IDs (no N+1 queries)
    linked_docs_stmt = (
        select(Deduction.document_id)
        .join(TaxProfile, Deduction.tax_profile_id == TaxProfile.id)
        .where(
            TaxProfile.user_id == current_user.id,
            Deduction.document_id.isnot(None),
        )
    )
    linked_res = await db.execute(linked_docs_stmt)
    linked_doc_ids = set(linked_res.scalars().all())

    return [
        DocumentRead.model_validate(doc).model_copy(
            update={"has_linked_deduction": doc.id in linked_doc_ids}
        )
        for doc in docs
    ]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    linked_stmt = (
        select(Deduction.id)
        .join(TaxProfile, Deduction.tax_profile_id == TaxProfile.id)
        .where(
            TaxProfile.user_id == current_user.id,
            Deduction.document_id == document_id,
        )
    )
    linked_res = await db.execute(linked_stmt)
    has_linked = linked_res.scalar_one_or_none() is not None

    return DocumentRead.model_validate(doc).model_copy(
        update={"has_linked_deduction": has_linked}
    )


@router.get("/{document_id}/preview")
async def preview_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    doc = await db.get(Document, document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    data = await storage.download_file(doc.file_path)
    ext = _extension(doc.original_filename)
    media_type = PREVIEW_MIME.get(ext, "application/octet-stream")

    safe_name = doc.original_filename.replace('"', "")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "Cache-Control": "private, max-age=60",
        },
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    doc = await db.get(Document, document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    await storage.delete_file(doc.file_path)
    await db.delete(doc)
    await db.commit()
    return Response(status_code=204)
