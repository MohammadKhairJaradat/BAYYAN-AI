# Knowledge Base

Source documents for the RAG pipeline. Only entries in [`manifest.json`](manifest.json) are ingested by [`scripts/ingest_knowledge_base.py`](../scripts/ingest_knowledge_base.py) into a versioned ChromaDB collection under `./data/chromadb`. The two included files are **demo fixtures, not official legal publications**. The user-supplied `../../Data/` tree is raw, unverified input; it is not an ingestion source.

## Subfolders

- **`law/`** — article/clause-structured source files; the included one is a demo fixture. Any future official law needs a verified source, edition, rights and effective date in the manifest.
- **`guidance/`** — guidance source files; the included one is a demo fixture.
- **`expert_commentary/`** — Transcribed expert audio/video (use [faster-whisper](https://github.com/SYSTRAN/faster-whisper) to transcribe before dropping the `.txt` here).
- **`staging/`** — candidate source records and extracts awaiting legal, text-quality, rights and date review. This folder is outside the ingestion manifest and its candidate contents are gitignored. See [staging/README.md](staging/README.md) and the [curation plan](../../docs/plans/proposed/bayyan-legal-corpus-curation.md).

Never promote a `Data/` derivative directly on the strength of its folder name or OCR success flag. One sampled local Article 9 extract says `230` where the [ISTD searchable law](https://istd.gov.jo/AR/List/%D9%82%D8%A7%D9%86%D9%88%D9%86_%D8%B6%D8%B1%D9%8A%D8%A8%D8%A9_%D8%A7%D9%84%D8%AF%D8%AE%D9%84) says `23000` for the cited ceiling; see the [source register](../../docs/knowledge-audit/official-source-register.md). Preserve originals and verify numeric text against official pages before citation.

## Supported file types

`.txt`, `.md`, `.pdf` (both text-based and scanned).

For scanned PDFs the script falls back to OCR via `pytesseract` + `pypdfium2`. **Arabic OCR requires the Tesseract Arabic language pack on the host machine:**

- macOS: `brew install tesseract tesseract-lang`
- Ubuntu/Debian: `sudo apt-get install tesseract-ocr tesseract-ocr-ara`
- Windows: install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and check the Arabic language during setup.

On this Windows workspace, Tesseract 5.4 was installed locally with `winget`. Arabic data were added from [the official `tessdata_fast` repository](https://github.com/tesseract-ocr/tessdata_fast/blob/main/ara.traineddata) under `%LOCALAPPDATA%\BAYYAN\tessdata` because Program Files is not writable by the ordinary shell. For a manual page check in PowerShell, use `& 'C:\Program Files\Tesseract-OCR\tesseract.exe' input.png stdout --tessdata-dir "$env:LOCALAPPDATA\BAYYAN\tessdata" -l ara+eng`. This setup is local and must be reproduced on another machine; it does **not** make OCR numerically reliable. An Article 9 trial garbled `23000`, so verify legal amounts against page images.

If the Arabic pack is missing, the script logs a warning and OCRs in English only — usable for English documents but useless for Arabic scans.

## How to run

From the repo root:

```bash
cd backend
uv run python scripts/ingest_knowledge_base.py            # incremental upsert
uv run python scripts/ingest_knowledge_base.py --dir /alt/path/to/kb # requires its own manifest.json
```

An unchanged source is skipped; a changed source gets a new content-hash revision while older chunks remain inactive for rollback. A model/dimension/schema change creates another collection and preserves the previous one. After ingestion, retrieval is available via `POST /api/v1/rag/query`; citations mark demo sources explicitly.
