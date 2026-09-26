"""
base.py — Shared interface and data types for the document extraction pipeline.

ALL extractors implement BaseExtractor and return ExtractionResult.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DocumentType(str, Enum):
    RECEIPT = "receipt"
    SALARY_SLIP = "salary_slip"
    BANK_STATEMENT = "bank_statement"
    UNKNOWN = "unknown"


class DeductionCategory(str, Enum):
    MEDICAL = "medical"
    EDUCATION = "education"
    RENT = "rent"
    HOUSING_INTEREST = "housing_interest"
    HOUSING_MURABAHA = "housing_murabaha"
    DONATIONS = "donations"
    INSURANCE = "insurance"
    PENSION = "pension"
    UNKNOWN = "unknown"


@dataclass
class ExtractionResult:
    vendor: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[dt.date] = None
    category: DeductionCategory = DeductionCategory.UNKNOWN
    document_type: DocumentType = DocumentType.UNKNOWN
    confidence: float = 0.0
    raw_text: Optional[str] = None
    extras: dict = field(default_factory=dict)
    extractor_backend: str = "unknown"
    error: Optional[str] = None

    @property
    def is_usable(self) -> bool:
        return (
            self.amount is not None
            and self.amount > 0
            and self.confidence >= 0.4
            and self.error is None
        )

    def to_jsonb(self) -> dict:
        return {
            "vendor": self.vendor,
            "amount": self.amount,
            "date": self.date.isoformat() if self.date else None,
            "category": self.category.value,
            "document_type": self.document_type.value,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
            "extras": self.extras,
            "extractor_backend": self.extractor_backend,
            "error": self.error,
        }

class BaseExtractor(ABC):
    @abstractmethod
    async def extract(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        document_type_hint: Optional[DocumentType] = None,
    ) -> ExtractionResult:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
