import datetime as dt

import pytest

import app.extraction.pipeline as pipeline
from app.config import settings
from app.extraction.base import (
    BaseExtractor,
    DeductionCategory,
    DocumentType,
    ExtractionResult,
)
from app.extraction.gemini_extractor import GeminiExtractor
from app.extraction.parsing import parse_model_output


class FakeExtractor(BaseExtractor):
    def __init__(self, name: str, result: ExtractionResult) -> None:
        self._name = name
        self.result = result
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def extract(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        document_type_hint: DocumentType | None = None,
    ) -> ExtractionResult:
        self.calls += 1
        return self.result


def _result(
    *,
    backend: str,
    confidence: float,
    error: str | None = None,
    amount: float | None = 42.0,
    category: DeductionCategory = DeductionCategory.MEDICAL,
) -> ExtractionResult:
    return ExtractionResult(
        vendor="Test vendor",
        amount=amount,
        date=dt.date(2026, 5, 23),
        category=category,
        document_type=DocumentType.RECEIPT,
        confidence=confidence,
        raw_text="raw text",
        extractor_backend=backend,
        error=error,
    )


@pytest.mark.asyncio
async def test_gemini_extractor_parses_valid_json(monkeypatch):
    monkeypatch.setattr(settings, "EXTRACTION_GEMINI_MODEL", "gemini-2.5-flash")
    extractor = GeminiExtractor()
    monkeypatch.setattr(
        extractor,
        "_call_api",
        lambda *_args: """
        {
          "vendor": "مستشفى الاختبار",
          "amount": 88.5,
          "date": "2026-05-23",
          "category": "medical",
          "document_type": "receipt",
          "confidence": 0.92,
          "raw_text": "إيصال طبي"
        }
        """,
    )

    result = await extractor.extract(b"image-bytes", mime_type="image/png")

    assert result.extractor_backend == "gemini-2.5-flash"
    assert result.vendor == "مستشفى الاختبار"
    assert result.amount == 88.5
    assert result.date == dt.date(2026, 5, 23)
    assert result.category == DeductionCategory.MEDICAL
    assert result.document_type == DocumentType.RECEIPT
    assert result.is_usable is True


@pytest.mark.asyncio
async def test_pipeline_falls_back_to_claude_when_gemini_errors(monkeypatch):
    gemini = FakeExtractor(
        "gemini-2.5-flash",
        _result(backend="gemini-2.5-flash", confidence=0.0, error="boom"),
    )
    claude = FakeExtractor(
        "claude-sonnet-4-20250514",
        _result(backend="claude-sonnet-4-20250514", confidence=0.9),
    )
    monkeypatch.setattr(pipeline, "_primary", gemini)
    monkeypatch.setattr(pipeline, "_fallback", claude)

    result = await pipeline.extract_document(b"image")

    assert result.extractor_backend == "claude-sonnet-4-20250514"
    assert gemini.calls == 1
    assert claude.calls == 1


@pytest.mark.asyncio
async def test_pipeline_falls_back_to_claude_on_low_confidence(monkeypatch):
    gemini = FakeExtractor(
        "gemini-2.5-flash",
        _result(backend="gemini-2.5-flash", confidence=0.2),
    )
    claude = FakeExtractor(
        "claude-sonnet-4-20250514",
        _result(backend="claude-sonnet-4-20250514", confidence=0.86),
    )
    monkeypatch.setattr(pipeline, "_primary", gemini)
    monkeypatch.setattr(pipeline, "_fallback", claude)

    result = await pipeline.extract_document(b"image", confidence_threshold=0.65)

    assert result.extractor_backend == "claude-sonnet-4-20250514"
    assert gemini.calls == 1
    assert claude.calls == 1


@pytest.mark.asyncio
async def test_force_fallback_skips_gemini(monkeypatch):
    gemini = FakeExtractor(
        "gemini-2.5-flash",
        _result(backend="gemini-2.5-flash", confidence=0.99),
    )
    claude = FakeExtractor(
        "claude-sonnet-4-20250514",
        _result(backend="claude-sonnet-4-20250514", confidence=0.88),
    )
    monkeypatch.setattr(pipeline, "_primary", gemini)
    monkeypatch.setattr(pipeline, "_fallback", claude)

    result = await pipeline.extract_document(b"image", force_fallback=True)

    assert result.extractor_backend == "claude-sonnet-4-20250514"
    assert gemini.calls == 0
    assert claude.calls == 1


@pytest.mark.asyncio
async def test_pipeline_returns_highest_confidence_when_both_fail(monkeypatch):
    gemini = FakeExtractor(
        "gemini-2.5-flash",
        _result(backend="gemini-2.5-flash", confidence=0.25, error="gemini fail"),
    )
    claude = FakeExtractor(
        "claude-sonnet-4-20250514",
        _result(backend="claude-sonnet-4-20250514", confidence=0.1, error="claude fail"),
    )
    monkeypatch.setattr(pipeline, "_primary", gemini)
    monkeypatch.setattr(pipeline, "_fallback", claude)

    result = await pipeline.extract_document(b"image")

    assert result.extractor_backend == "gemini-2.5-flash"
    assert result.error == "gemini fail"


def test_parser_handles_markdown_fenced_json():
    result = parse_model_output(
        """```json
        {
          "vendor": "School",
          "amount": 120,
          "date": "2026-05-23",
          "category": "education",
          "document_type": "receipt",
          "confidence": 0.77,
          "raw_text": "receipt text"
        }
        ```""",
        backend="parser-test",
    )

    assert result.error is None
    assert result.category == DeductionCategory.EDUCATION
    assert result.amount == 120.0


def test_parser_handles_trailing_comma_json():
    result = parse_model_output(
        """
        {
          "vendor": "Clinic",
          "amount": 12.5,
          "date": "2026-05-23",
          "category": "medical",
          "document_type": "receipt",
          "confidence": 0.7,
          "raw_text": "receipt text",
        }
        """,
        backend="parser-test",
    )

    assert result.error is None
    assert result.vendor == "Clinic"
    assert result.category == DeductionCategory.MEDICAL
