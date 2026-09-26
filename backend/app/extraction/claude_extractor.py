"""
Fallback document extractor using Claude vision.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

from app.config import settings

from .base import BaseExtractor, DocumentType, ExtractionResult
from .parsing import parse_model_output
from .prompts import EXTRACTION_SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

_SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}


class ClaudeExtractor(BaseExtractor):
    def __init__(self) -> None:
        self._model_id = settings.EXTRACTION_CLAUDE_MODEL

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
            logger.exception("Claude extraction failed")
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
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic is not installed. Run: uv sync") from exc

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

        normalized_mime = _normalize_image_mime_type(mime_type)
        with anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=30, max_retries=0) as client:
            response = client.messages.create(
                model=self._model_id,
                max_tokens=1024,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": normalized_mime,
                                    "data": base64.b64encode(image_bytes).decode("ascii"),
                                },
                            },
                            {"type": "text", "text": build_user_prompt(hint)},
                        ],
                    }
                ],
            )
        return _extract_text(response)


def _normalize_image_mime_type(mime_type: str) -> str:
    normalized = (mime_type or "image/jpeg").split(";", 1)[0].strip().lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if normalized not in _SUPPORTED_IMAGE_MIME_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_IMAGE_MIME_TYPES))
        raise ValueError(
            f"Claude vision fallback supports image uploads only. "
            f"Got {mime_type!r}; supported: {supported}."
        )
    return normalized


def _extract_text(response) -> str:
    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()
