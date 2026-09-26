import asyncio
from typing import Optional
import datetime as dt

from .base import (
    BaseExtractor,
    DeductionCategory,
    DocumentType,
    ExtractionResult,
)

class MockExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "mock-extractor"

    async def extract(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        document_type_hint: Optional[DocumentType] = None,
    ) -> ExtractionResult:
        # Simulate network/processing delay
        await asyncio.sleep(2.0)

        return ExtractionResult(
            vendor="مدرسة وروضة براعم الأمل (Mocked)",
            amount=100.0,
            date=dt.date(2024, 10, 27),
            category=DeductionCategory.EDUCATION,
            document_type=DocumentType.RECEIPT,
            confidence=0.99,
            raw_text="This is a mocked extraction response for testing purposes.",
            extractor_backend=self.name,
        )
