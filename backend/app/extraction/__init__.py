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
from .pipeline import extract_document, needs_user_verification

__all__ = [
    "extract_document",
    "needs_user_verification",
    "ExtractionResult",
    "DocumentType",
    "DeductionCategory",
    "BaseExtractor",
    "GeminiExtractor",
    "ClaudeExtractor",
]
