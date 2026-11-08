"""
app.extraction — Document extraction pipeline public API.
"""

from __future__ import annotations

from .base import (
    BaseExtractor,
    DeductionCategory,
    DocumentType,
    ExtractionResult,
)
from .claude_extractor import ClaudeExtractor
from .gemini_extractor import GeminiExtractor
from .parsing import validate_extraction_fields
from .pipeline import extract_document, needs_user_verification

__all__ = [
    "extract_document",
    "needs_user_verification",
    "validate_extraction_fields",
    "ExtractionResult",
    "DocumentType",
    "DeductionCategory",
    "BaseExtractor",
    "GeminiExtractor",
    "ClaudeExtractor",
]
