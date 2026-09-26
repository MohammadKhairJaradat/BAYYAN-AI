"""
Robust JSON parsing for model-generated extraction output.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from .base import DeductionCategory, DocumentType, ExtractionResult


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
            date_val = dt.date.fromisoformat(str(raw_date))
        except ValueError:
            pass

    amount = None
    raw_amount = data.get("amount")
    if raw_amount is not None:
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            pass

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
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    extras = data.get("extras")
    if not isinstance(extras, dict):
        extras = {}

    return ExtractionResult(
        vendor=data.get("vendor"),
        amount=amount,
        date=date_val,
        category=category,
        document_type=doc_type,
        confidence=confidence,
        raw_text=data.get("raw_text"),
        extras=extras,
        extractor_backend=backend,
    )
