"""
Robust JSON parsing and field validation for model-generated extraction output.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from typing import Any

from .base import DeductionCategory, DocumentType, ExtractionResult

MIN_INVOICE_YEAR = 1990


def _is_valid_invoice_date(value: dt.date) -> bool:
    max_year = dt.date.today().year + 1
    return MIN_INVOICE_YEAR <= value.year <= max_year


def parse_model_output(raw_output: str, backend: str) -> ExtractionResult:
    cleaned = re.sub(r"```(?:json)?", "", raw_output).strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return ExtractionResult(
                extractor_backend=backend,
                confidence=0.0,
                raw_text=raw_output,
                error=f"No JSON found in output. Raw: {raw_output[:200]}",
            )
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return ExtractionResult(
                extractor_backend=backend,
                confidence=0.0,
                raw_text=raw_output,
                error=f"JSON parse failed. Raw: {raw_output[:200]}",
            )

    if not isinstance(data, dict):
        return ExtractionResult(
            extractor_backend=backend,
            confidence=0.0,
            raw_text=raw_output,
            error=f"JSON parse failed. Expected object, got {type(data).__name__}.",
        )

    return extraction_result_from_mapping(data, backend=backend)


def extraction_result_from_mapping(data: dict[str, Any], backend: str) -> ExtractionResult:
    date_val = None
    raw_date = data.get("date")
    if raw_date:
        try:
            parsed_date = dt.date.fromisoformat(str(raw_date).strip())
            if _is_valid_invoice_date(parsed_date):
                date_val = parsed_date
        except ValueError:
            pass

    amount = None
    raw_amount = data.get("amount")
    if raw_amount is not None and not isinstance(raw_amount, bool):
        try:
            parsed_amount = float(raw_amount)
            if math.isfinite(parsed_amount) and parsed_amount >= 0:
                amount = parsed_amount
        except (TypeError, ValueError):
            pass

    raw_vendor = data.get("vendor")
    vendor = raw_vendor.strip() if isinstance(raw_vendor, str) and raw_vendor.strip() else None

    try:
        category = DeductionCategory(data.get("category", "unknown"))
    except ValueError:
        category = DeductionCategory.UNKNOWN

    try:
        doc_type = DocumentType(data.get("document_type", "unknown"))
    except ValueError:
        doc_type = DocumentType.UNKNOWN

    try:
        confidence = float(data.get("confidence", 0.5))
        if not math.isfinite(confidence):
            confidence = 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    extras = data.get("extras")
    if not isinstance(extras, dict):
        extras = {}

    return ExtractionResult(
        vendor=vendor,
        amount=amount,
        date=date_val,
        category=category,
        document_type=doc_type,
        confidence=confidence,
        raw_text=data.get("raw_text"),
        extras=extras,
        extractor_backend=backend,
    )


def validate_extraction_fields(result: ExtractionResult) -> list[str]:
    """Run light validation checks on extracted invoice/receipt fields.

    Returns a list of failed check identifiers (empty list when all checks pass).
    """
    issues: list[str] = []
    if result.error is not None:
        issues.append("extractor_error")
    if result.amount is None or not math.isfinite(result.amount) or result.amount <= 0:
        issues.append("missing_or_non_positive_amount")
    if result.category == DeductionCategory.UNKNOWN:
        issues.append("unknown_category")
    if result.document_type == DocumentType.UNKNOWN:
        issues.append("unknown_document_type")
    if not result.vendor or not str(result.vendor).strip():
        issues.append("missing_vendor")
    if result.date is None or not _is_valid_invoice_date(result.date):
        issues.append("missing_or_out_of_range_date")
    if not math.isfinite(result.confidence) or result.confidence < 0.4:
        issues.append("low_confidence")
    return issues
