#!/usr/bin/env python3
"""
ingest_knowledge_base.py — One-time (or on-update) ingestion script.

Reads sources listed in the knowledge-base manifest, chunks them using
legal-structure-aware chunking, validates chunks, and upserts one revision at a time.

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

from app.rag.chunker import (
    LegalChunk,
    SourceType,
    chunk_guidance_document,
    chunk_legal_document,
    validate_chunk,
)
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
# Validation & pipeline runner
# ─────────────────────────────────────────────────────────────────────────────

def _filter_and_deduplicate_chunks(
    chunks: list[LegalChunk],
) -> tuple[list[LegalChunk], int, int]:
    """Validate chunks and deduplicate exact duplicate text within the same source.

    Returns (valid_unique_chunks, rejected_validation_count, duplicate_count).
    """
    valid_unique: list[LegalChunk] = []
    seen_texts: set[str] = set()
    rejected = 0
    duplicates = 0

    for chunk in chunks:
        issues = validate_chunk(chunk)
        if issues:
            rejected += 1
            logger.warning(
                "  Dropping invalid chunk from %s (%s): %s",
                chunk.source_file,
                chunk.citation,
                ", ".join(issues),
            )
            continue
        norm_text = chunk.text.strip()
        if norm_text in seen_texts:
            duplicates += 1
            logger.debug(
                "  Deduplicating repeated chunk in %s (%s)",
                chunk.source_file,
                chunk.citation,
            )
            continue
        seen_texts.add(norm_text)
        valid_unique.append(chunk)

    return valid_unique, rejected, duplicates


def run_ingestion(
    kb_dir: Path = KNOWLEDGE_BASE_DIR,
    store: VectorStore | None = None,
) -> dict:
    """Ingest all manifest-listed sources with validation and content-hash deduplication.

    Returns a structured ingestion summary dictionary.
    """
    if not kb_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_dir}")

    manifest_path = kb_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Knowledge-base manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sources"), list):
        raise ValueError("Unsupported knowledge-base manifest")

    if store is None:
        store = VectorStore()

    total_chunks_generated = 0
    total_chunks_valid = 0
    total_chunks_rejected = 0
    total_chunks_dedup = 0
    total_chunks_upserted = 0
    files_processed = 0
    files_upserted = 0
    files_skipped_unchanged = 0
    source_reports: list[dict] = []

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

        raw_chunks = ingest_file(
            fpath, source_type, chunker_type, entry.get("law_year"), kb_dir,
            entry.get("effective_date"),
        )
        total_chunks_generated += len(raw_chunks)
        chunks, rejected_count, dedup_count = _filter_and_deduplicate_chunks(raw_chunks)
        total_chunks_valid += len(chunks)
        total_chunks_rejected += rejected_count
        total_chunks_dedup += dedup_count

        if not chunks:
            logger.warning("No valid chunks produced; leaving prior index revision intact: %s", relative)
            source_reports.append({
                "file": relative,
                "type": source_type.value,
                "status": entry["status"],
                "source_hash": None,
                "chunks_generated": len(raw_chunks),
                "chunks_valid": 0,
                "chunks_upserted": 0,
                "action": "empty",
            })
            continue

        content = fpath.read_bytes() + "\n".join(chunk.text for chunk in chunks).encode()
        source_hash = hashlib.sha256(content).hexdigest()
        upserted = store.upsert_source(
            chunks, source_hash=source_hash, source_title=entry["title"],
            source_status=entry["status"], source_url=entry.get("source_url", ""),
        )
        files_processed += 1
        total_chunks_upserted += upserted
        if upserted > 0:
            files_upserted += 1
            action = "upserted"
        else:
            files_skipped_unchanged += 1
            action = "skipped_unchanged"
            logger.info("  Skipped unchanged source (hash %s...): %s", source_hash[:12], relative)

        source_reports.append({
            "file": relative,
            "type": source_type.value,
            "status": entry["status"],
            "source_hash": source_hash,
            "chunks_generated": len(raw_chunks),
            "chunks_valid": len(chunks),
            "chunks_rejected_validation": rejected_count,
            "chunks_deduplicated": dedup_count,
            "chunks_upserted": upserted,
            "action": action,
        })

    report = {
        "manifest_sources_total": len(manifest["sources"]),
        "files_processed": files_processed,
        "files_upserted": files_upserted,
        "files_skipped_unchanged": files_skipped_unchanged,
        "chunks_generated": total_chunks_generated,
        "chunks_valid": total_chunks_valid,
        "chunks_rejected_validation": total_chunks_rejected,
        "chunks_deduplicated_within_source": total_chunks_dedup,
        "chunks_upserted": total_chunks_upserted,
        "collection_name": store.collection_name,
        "collection_total_chunks": store.count(),
        "sources": source_reports,
    }

    logger.info(
        "\n✓ Ingestion complete.\n"
        "   Files processed          : %d (upserted: %d, skipped unchanged: %d)\n"
        "   Chunks generated / valid : %d / %d (rejected: %d, deduped: %d)\n"
        "   Chunks upserted          : %d\n"
        "   Collection total         : %d",
        files_processed,
        files_upserted,
        files_skipped_unchanged,
        total_chunks_generated,
        total_chunks_valid,
        total_chunks_rejected,
        total_chunks_dedup,
        total_chunks_upserted,
        store.count(),
    )
    return report


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
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Optional path to write JSON ingestion report",
    )
    args = parser.parse_args()

    try:
        report = run_ingestion(kb_dir=args.dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Saved ingestion report to %s", args.report_json)


if __name__ == "__main__":
    main()
