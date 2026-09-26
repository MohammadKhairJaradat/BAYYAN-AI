"""
pipeline.py — Document extraction pipeline orchestrator.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings

from .base import BaseExtractor, DocumentType, ExtractionResult
from .claude_extractor import ClaudeExtractor
from .gemini_extractor import GeminiExtractor

logger = logging.getLogger(__name__)

_primary: Optional[GeminiExtractor] = None
_fallback: Optional[ClaudeExtractor] = None


def _get_primary() -> GeminiExtractor:
    global _primary
    if _primary is None:
        _primary = GeminiExtractor()
    return _primary


def _get_fallback() -> ClaudeExtractor:
    global _fallback
    if _fallback is None:
        _fallback = ClaudeExtractor()
    return _fallback


async def extract_document(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    document_type_hint: Optional[DocumentType] = None,
    force_fallback: bool = False,
    confidence_threshold: Optional[float] = None,
) -> ExtractionResult:
    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else settings.EXTRACTION_CONFIDENCE_THRESHOLD
    )

    if force_fallback:
        logger.info("Forced fallback: using Claude extractor directly.")
        result = await _run_extractor(
            _get_fallback(), image_bytes, mime_type, document_type_hint
        )
        return result

    logger.info("Extracting with Gemini primary: %s", _get_primary().name)
    primary_result = await _run_extractor(
        _get_primary(), image_bytes, mime_type, document_type_hint
    )

    if primary_result.error:
        logger.warning(
            "Primary extractor returned error: %s. Escalating to fallback.",
            primary_result.error,
        )
    elif primary_result.confidence >= threshold:
        logger.info(
            "Primary extractor succeeded. confidence=%.2f (threshold=%.2f)",
            primary_result.confidence,
            threshold,
        )
        return primary_result
    else:
        logger.info(
            "Primary extractor confidence too low (%.2f < %.2f). Escalating to fallback.",
            primary_result.confidence,
            threshold,
        )

    logger.info("Escalating to Claude fallback: %s", _get_fallback().name)
    fallback_result = await _run_extractor(
        _get_fallback(), image_bytes, mime_type, document_type_hint
    )

    if fallback_result.error:
        logger.error(
            "Fallback extractor also failed: %s. Returning best available result.",
            fallback_result.error,
        )
        if (primary_result.confidence or 0) >= (fallback_result.confidence or 0):
            return primary_result
        return fallback_result

    logger.info(
        "Fallback extractor succeeded. confidence=%.2f",
        fallback_result.confidence,
    )
    return fallback_result


async def _run_extractor(
    extractor: BaseExtractor,
    image_bytes: bytes,
    mime_type: str,
    hint: Optional[DocumentType],
) -> ExtractionResult:
    return await extractor.extract(image_bytes, mime_type, hint)


def needs_user_verification(result: ExtractionResult) -> bool:
    return (
        result.confidence < settings.EXTRACTION_CONFIDENCE_THRESHOLD
        or result.amount is None
        or result.category.value == "unknown"
        or result.error is not None
    )
