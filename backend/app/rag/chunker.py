"""
chunker.py — Legal-structure-aware text chunker for Jordanian tax law.

Splits documents by المادة (article), فقرة (clause), and بند (sub-clause).
Each chunk carries full metadata so retrieval can surface precise legal citations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceType(str, Enum):
    LAW = "law"
    GUIDANCE = "guidance"
    EXPERT_COMMENTARY = "expert_commentary"


@dataclass
class LegalChunk:
    """A single retrievable unit from the knowledge base."""

    text: str
    text_ar: Optional[str]
    source_file: str
    source_type: SourceType
    article_number: Optional[str] = None
    chapter: Optional[str] = None
    clause: Optional[str] = None
    topic: Optional[str] = None
    law_year: Optional[int] = None
    effective_date: Optional[str] = None
    page_number: Optional[int] = None
    keywords: list[str] = field(default_factory=list)

    def to_chroma_document(self) -> dict:
        return {
            "text": self.text,
            "metadata": {
                "source_file": self.source_file,
                "source_type": self.source_type.value,
                "article_number": self.article_number or "",
                "chapter": self.chapter or "",
                "clause": self.clause or "",
                "topic": self.topic or "",
                "law_year": str(self.law_year) if self.law_year else "",
                "effective_date": self.effective_date or "",
                "page_number": str(self.page_number) if self.page_number else "",
                "keywords": ",".join(self.keywords),
            },
        }

    @property
    def citation(self) -> str:
        parts = []
        if self.article_number:
            parts.append(f"المادة {self.article_number}")
        if self.clause:
            parts.append(self.clause)
        if self.chapter:
            parts.append(self.chapter)
        return " - ".join(parts) if parts else self.source_file


_ARTICLE_AR = re.compile(
    r"(?:^|\n)\s*(?:المادة|مادة)\s*[(\[]?\s*(\d+(?:[/\\]\w+)?)\s*[)\]]?",
    re.MULTILINE,
)

_CHAPTER_AR = re.compile(
    r"(?:^|\n)\s*(الفصل\s+(?:الأول|الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر|\w+))",
    re.MULTILINE,
)

_CLAUSE = re.compile(r"\n\s*[(\[]([أبجدهوزحطيابتثجح]|\d+)[)\]]")

_ARTICLE_EN = re.compile(
    r"(?:^|\n)\s*(?:Article|Art\.? )\s+(\d+(?:\.\d+)?)",
    re.MULTILINE,
)


def _extract_keywords(text: str) -> list[str]:
    terms = [
        "ضريبة", "إعفاء", "خصم", "دخل", "راتب", "تأجير", "استثمار",
        "وعاء", "مكلف", "إقرار", "فاتورة", "وثيقة", "تأمين", "تبرع",
        "فوائد", "أرباح", "رسوم", "غرامة", "استرداد", "معدل",
        "deduction", "exemption", "income", "salary", "tax", "taxable",
        "filing", "return", "bracket", "rate", "allowance",
    ]
    found = [t for t in terms if t in text]
    found += re.findall(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:دينار|JD|%|٪)?\b", text)
    return list(dict.fromkeys(found))


def _split_by_articles(text: str, pattern: re.Pattern) -> list[tuple[str, str]]:
    matches = list(pattern.finditer(text))
    if not matches:
        return [("", text)]

    chunks = []
    for i, m in enumerate(matches):
        article_num = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append((article_num, text[start:end].strip()))
    return chunks


def _split_by_clauses(article_text: str) -> list[tuple[str, str]]:
    parts = _CLAUSE.split(article_text)
    if len(parts) <= 1:
        return [("", article_text)]

    result = [("", parts[0].strip())] if parts[0].strip() else []
    for i in range(1, len(parts), 2):
        label = f"({parts[i]})"
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            result.append((label, body))
    return result


def chunk_legal_document(
    text: str,
    source_file: str,
    source_type: SourceType = SourceType.LAW,
    law_year: Optional[int] = None,
    effective_date: Optional[str] = None,
    min_chars: int = 80,
) -> list[LegalChunk]:
    chunks: list[LegalChunk] = []
    current_chapter: Optional[str] = None

    chapter_positions = {m.start(): m.group(1) for m in _CHAPTER_AR.finditer(text)}
    sorted_chapter_starts = sorted(chapter_positions)

    def _chapter_at(pos: int) -> Optional[str]:
        relevant = [s for s in sorted_chapter_starts if s <= pos]
        return chapter_positions[relevant[-1]] if relevant else None

    article_pattern = _ARTICLE_AR if _ARTICLE_AR.search(text) else _ARTICLE_EN
    article_splits = _split_by_articles(text, article_pattern)

    for art_num, art_text in article_splits:
        pos = text.find(art_text[:40]) if art_text else 0
        current_chapter = _chapter_at(pos)
        clause_splits = _split_by_clauses(art_text)

        for clause_label, clause_text in clause_splits:
            if len(clause_text) < min_chars:
                continue
            chunk = LegalChunk(
                text=clause_text,
                text_ar=clause_text if _looks_arabic(clause_text) else None,
                source_file=source_file,
                source_type=source_type,
                article_number=art_num or None,
                chapter=current_chapter,
                clause=clause_label or None,
                law_year=law_year,
                effective_date=effective_date,
                keywords=_extract_keywords(clause_text),
            )
            chunks.append(chunk)

    if not chunks and len(text) >= min_chars:
        chunks.append(
            LegalChunk(
                text=text,
                text_ar=text if _looks_arabic(text) else None,
                source_file=source_file,
                source_type=source_type,
                law_year=law_year,
                effective_date=effective_date,
                keywords=_extract_keywords(text),
            )
        )

    return chunks


def _looks_arabic(text: str) -> bool:
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    return arabic_chars / max(len(text), 1) > 0.2


def chunk_guidance_document(
    text: str,
    source_file: str,
    law_year: Optional[int] = None,
    source_type: SourceType = SourceType.GUIDANCE,
) -> list[LegalChunk]:
    MAX_CHARS = 1200
    MIN_CHARS = 80
    raw_sections = re.split(r"\n{2,}|\n(?=#{1,3}\s)", text)
    chunks: list[LegalChunk] = []
    buffer = ""

    for section in raw_sections:
        section = section.strip()
        if not section:
            continue
        if len(buffer) + len(section) > MAX_CHARS and len(buffer) >= MIN_CHARS:
            chunks.append(
                LegalChunk(
                    text=buffer,
                    text_ar=buffer if _looks_arabic(buffer) else None,
                    source_file=source_file,
                    source_type=source_type,
                    law_year=law_year,
                    keywords=_extract_keywords(buffer),
                )
            )
            buffer = section
        else:
            buffer = f"{buffer}\n\n{section}" if buffer else section

    if buffer.strip():
        chunks.append(
            LegalChunk(
                text=buffer.strip(),
                text_ar=buffer.strip() if _looks_arabic(buffer) else None,
                source_file=source_file,
                source_type=source_type,
                law_year=law_year,
                keywords=_extract_keywords(buffer.strip()),
            )
        )

    return [c for c in chunks if len(c.text) >= MIN_CHARS]
