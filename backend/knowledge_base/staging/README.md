# Candidate corpus staging — not indexed

This directory is for reviewed **preparation work**, not for automatic RAG ingestion. `../manifest.json` is the sole ingestion list and currently names only the two existing demo fixtures. Do not add a candidate to it merely because its PDF or extracted text exists here.

Preserve original files under the repository's `Data/` directory. For each candidate, record the original relative path and SHA-256, official publisher and URL, document title/number/edition, publication and effective dates, applicable tax years, scope (individual/company/sales/etc.), authority class (law/regulation/official guidance/commentary/example), extraction method and page mapping, Arabic OCR defects, rights note, and review decision. Unknown values must stay unknown. Do not use `Source_of_Truth` in a path as evidence of legal accuracy.

Only Codex's reviewed promotion step may move a candidate into `law/` or `guidance/`. Public social-media material belongs in an anonymized question/evaluation set outside the legal index. No Chroma write is authorized by staging.

Use one `*.source.json` record for each staged file. Run `uv run python scripts/validate_knowledge_candidates.py` from `backend/` to check file presence, SHA-256, byte length, HTTPS URL and date syntax without loading embeddings or writing Chroma. A `reviewed` record additionally needs a government URL, gazette/source issue, effective date, tax-year start, review date/reviewer and documented rights basis. Passing this validator is a **technical** check, not a legal review or permission to add the file to `manifest.json`.
