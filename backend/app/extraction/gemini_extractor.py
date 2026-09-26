"""
Primary document extractor using Gemini vision.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import settings

from .base import BaseExtractor, DocumentType, ExtractionResult
from .parsing import parse_model_output
from .prompts import (
    EXTRACTION_RESPONSE_SCHEMA,
    EXTRACTION_SYSTEM_PROMPT,
    build_user_prompt,
)

logger = logging.getLogger(__name__)


class GeminiExtractor(BaseExtractor):
    def __init__(self) -> None:
        self._model_id = settings.EXTRACTION_GEMINI_MODEL

    @property
    def name(self) -> str:
        return self._model_id

    async def extract(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        document_type_hint: Optional[DocumentType] = None,
    ) -> ExtractionResult:
        try:
            raw_output = await asyncio.to_thread(
                self._call_api,
                image_bytes,
                mime_type,
                document_type_hint,
            )
            return parse_model_output(raw_output, backend=self.name)
        except Exception as exc:
            logger.exception("Gemini extraction failed")
            return ExtractionResult(
                extractor_backend=self.name,
                confidence=0.0,
                error=str(exc),
            )

    def _call_api(
        self,
        image_bytes: bytes,
        mime_type: str,
        hint: Optional[DocumentType],
    ) -> str:
        from app.integrations.ai.google import generate

        api_key = settings.GOOGLE_AI_API_KEY or settings.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError(
                "Document extraction needs GOOGLE_AI_API_KEY or GEMINI_API_KEY. "
                "Add a Google AI Studio key to backend/.env and restart the backend."
            )

        response_schema = EXTRACTION_RESPONSE_SCHEMA
        try:
            return generate(
                api_key=api_key, model=self._model_id,
                prompt=build_user_prompt(hint),
                system_instruction=EXTRACTION_SYSTEM_PROMPT,
                max_output_tokens=1024, temperature=0,
                response_mime_type="application/json",
                response_schema=response_schema,
                media=image_bytes, media_mime_type=mime_type,
            )
        except Exception as exc:
            if "response_schema" not in str(exc) and "nullable" not in str(exc):
                raise
            logger.warning(
                "Gemini response_schema was rejected; retrying with JSON MIME only: %s",
                exc,
            )
            return generate(
                api_key=api_key, model=self._model_id,
                prompt=build_user_prompt(hint),
                system_instruction=EXTRACTION_SYSTEM_PROMPT,
                max_output_tokens=1024, temperature=0,
                response_mime_type="application/json",
                media=image_bytes, media_mime_type=mime_type,
            )
