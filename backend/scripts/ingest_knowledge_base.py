#!/usr/bin/env python3
"""
ingest_knowledge_base.py — One-time (or on-update) ingestion script.

Reads sources listed in the knowledge-base manifest, chunks them using
legal-structure-aware chunking, and upserts one revision at a time.

Supports:
    - .txt / .md  — read directly
    - .pdf (text) — extract with pdfplumber
    - .pdf (scan) — OCR with pytesseract (Arabic + English)

Run:
    uv run python backend/scripts/ingest_knowledge_base.py

Knowledge base directory structure:
    knowledge_base/
        law/               # Jordanian tax law PDFs/text (Arabic)
        guidance/          # ISTD circulars, practitioner guides
        expert_commentary/ # Transcribed expert audio/video
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.chunker import SourceType, chunk_guidance_document, chunk_legal_document
from app.rag.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingest")

KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"

DIRECTORY_CONFIG: dict[str, tuple[SourceType, str]] = {
    "law":               (SourceType.LAW,               "legal"),
    "guidance":          (SourceType.GUIDANCE,          "guidance"),
    "expert_commentary": (SourceType.EXPERT_COMMENTARY, "guidance"),
}

# Minimum characters to consider a page "has text" (vs scanned)
MIN_TEXT_CHARS = 50


# ─────────────────────────────────────────────────────────────────────────────
# PDF extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_pdf_pages(path: Path) -> list[str]:
    """
    Extract text from a PDF.
    - Tries pdfplumber first (fast, good for text PDFs).
    - Falls back to OCR (pytesseract) page-by-page for scanned pages.
    Returns page text separately so citations can retain page numbers.
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber not installed. Run: uv add pdfplumber")

    full_text_parts: list[str | None] = []
    scanned_pages: list[int] = []

    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        logger.info("  PDF has %d pages: %s", total, path.name)

        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            text = text.strip()

            if len(text) >= MIN_TEXT_CHARS:
                full_text_parts.append(text)
            else:
                # Page likely scanned — queue for OCR
                scanned_pages.append(i - 1)  # 0-indexed for later
                full_text_parts.append(None)  # placeholder

    # OCR scanned pages
    if scanned_pages:
        logger.info(
            "  %d scanned page(s) detected — running OCR (Arabic+English)...",
            len(scanned_pages),
        )
        ocr_results = _ocr_pages(path, scanned_pages)
        for page_idx in scanned_pages:
            full_text_parts[page_idx] = ocr_results.get(page_idx, "")

    return [page or "" for page in full_text_parts]


def _ocr_pages(path: Path, page_indices: list[int]) -> dict[int, str]:
    """
    Run OCR on specific pages of a PDF.
    Uses pytesseract with Arabic + English language support.
    Returns dict of {page_index: ocr_text}.
    """
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError(
            "pytesseract or Pillow not installed. Run: uv add pytesseract pillow"
        )

    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError(
            "pypdfium2 not installed. Run: uv add pypdfium2"
        )

    results: dict[int, str] = {}

    doc = pdfium.PdfDocument(str(path))
    for page_idx in page_indices:
        try:
            page = doc[page_idx]
            # Render at 200 DPI for good OCR accuracy
            bitmap = page.render(scale=200 / 72)
            pil_image = bitmap.to_pil()

            # OCR with Arabic + English
            # lang="ara+eng" requires Tesseract Arabic language pack installed
            try:
                text = pytesseract.image_to_string(
                    pil_image,
                    lang="ara+eng",
                    config="--oem 3 --psm 6",
                )
            except pytesseract.TesseractError:
                # Fallback: English only if Arabic pack not installed
                logger.warning(
                    "Arabic OCR not available — falling back to English only. "
                    "Install Tesseract Arabic pack for better Arabic results."
                )
                text = pytesseract.image_to_string(
                    pil_image,
                    lang="eng",
                    config="--oem 3 --psm 6",
                )

            results[page_idx] = text.strip()
            logger.debug("  OCR page %d: %d chars", page_idx + 1, len(text))

        except Exception as exc:
            logger.warning("  OCR failed for page %d: %s", page_idx + 1, exc)
            results[page_idx] = ""

    doc.close()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# File ingestion
# ─────────────────────────────────────────────────────────────────────────────

def ingest_file(
    path: Path,
    source_type: SourceType,
    chunker_type: str,
    law_year: int | None,
    kb_dir: Path,
    effective_date: str | None = None,
) -> list:
    """Read a file and return its LegalChunk list."""
    suffix = path.suffix.lower()

    # ── Extract text ────────────────────────────────────────────────────────
    if suffix == ".pdf":
        try:
            pages = _extract_pdf_pages(path)
        except Exception as exc:
            logger.error("  Failed to extract PDF %s: %s", path.name, exc)
            return []
    elif suffix in (".txt", ".md"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        pages = [text]
    else:
        logger.debug("  Skipping unsupported file type: %s", path.name)
        return []

    if not any(page.strip() for page in pages):
        logger.warning("  Skipping — no text extracted: %s", path.name)
        return []

    relative_name = path.relative_to(kb_dir).as_posix()
    logger.info("  Extracted %d chars from %s", sum(map(len, pages)), relative_name)

    # ── Chunk ───────────────────────────────────────────────────────────────
    chunks = []
    for page_number, text in enumerate(pages, start=1):
        if not text.strip():
            continue
        if chunker_type == "legal":
            page_chunks = chunk_legal_document(
                text=text, source_file=relative_name, source_type=source_type,
                law_year=law_year, effective_date=effective_date,
            )
        else:
            page_chunks = chunk_guidance_document(
                text=text, source_file=relative_name, law_year=law_year,
                source_type=source_type,
            )
        for chunk in page_chunks:
            chunk.effective_date = effective_date
            chunk.page_number = page_number if suffix == ".pdf" else None
        chunks.extend(page_chunks)

    logger.info("  → %d chunks from %s", len(chunks), relative_name)
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest knowledge base into ChromaDB")
    parser.add_argument(
        "--dir",
        type=Path,
        default=KNOWLEDGE_BASE_DIR,
        help="Path to knowledge_base directory",
    )
    args = parser.parse_args()

    kb_dir: Path = args.dir
    if not kb_dir.exists():
        logger.error("Knowledge base directory not found: %s", kb_dir)
        sys.exit(1)

    manifest_path = kb_dir / "manifest.json"
    if not manifest_path.is_file():
        logger.error("Knowledge-base manifest not found: %s", manifest_path)
        sys.exit(1)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sources"), list):
        raise ValueError("Unsupported knowledge-base manifest")
    store = VectorStore()
    total_chunks = 0
    total_files = 0
    seen_files: set[str] = set()
    for entry in manifest["sources"]:
        relative = entry["file"]
        if relative in seen_files:
            raise ValueError(f"Duplicate source in manifest: {relative}")
        seen_files.add(relative)
        fpath = (kb_dir / relative).resolve()
        if not fpath.is_relative_to(kb_dir.resolve()) or not fpath.is_file():
            raise ValueError(f"Missing or outside knowledge-base source: {relative}")
        source_type = SourceType(entry["type"])
        folder = relative.split("/", 1)[0]
        configured_type, chunker_type = DIRECTORY_CONFIG[folder]
        if source_type != configured_type:
            raise ValueError(f"Source type disagrees with folder: {relative}")
        if entry["status"] not in {"demo", "unreviewed", "reviewed"}:
            raise ValueError(f"Invalid review status: {relative}")
        chunks = ingest_file(
            fpath, source_type, chunker_type, entry.get("law_year"), kb_dir,
            entry.get("effective_date"),
        )
        if not chunks:
            logger.warning("No chunks produced; leaving prior index revision intact: %s", relative)
            continue
        content = fpath.read_bytes() + "\n".join(chunk.text for chunk in chunks).encode()
        source_hash = hashlib.sha256(content).hexdigest()
        total_chunks += store.upsert_source(
            chunks, source_hash=source_hash, source_title=entry["title"],
            source_status=entry["status"], source_url=entry.get("source_url", ""),
        )
        total_files += 1

    logger.info(
        "\n✓ Ingestion complete.\n"
        "   Files processed : %d\n"
        "   Chunks upserted : %d\n"
        "   Collection total: %d",
        total_files,
        total_chunks,
        store.count(),
    )


if __name__ == "__main__":
    main()
