# Validation on 14 October 2026

The checks below use synthetic taxpayer data and the bundled demo knowledge-base fixtures. They verify application behavior against the coded rules, not legal approval or accuracy on arbitrary real-world documents.

## Automated checks

| Check | Result |
|---|---|
| Backend pytest suite, including five PostgreSQL integration tests | 262 passed; 2 skipped |
| Calculation-focused subset: `test_tax_engine.py`, `test_s07_decimal.py`, `test_s07_legacy_golden.py` | 42 passed |
| Frontend Vitest suite | 67 passed |
| Frontend ESLint and production build | Passed |
| Fresh PostgreSQL database migrations through Alembic revision 022 | Passed |

The two skipped checks require local staging documents or an evaluation dataset that are not included in a clean repository checkout. They are not counted as passes.

The PostgreSQL processing test now follows the current confirmation workflow: concurrent extraction proposes values without creating deductions; a separately confirmed deduction remains linked on retry, and the database rejects duplicate document links.

## Gemini smoke checks

Each of these seven scenarios completed successfully on its latest execution with Gemini 2.5 Flash:

1. Arabic introductory chat.
2. A school-fee question using the real local E5/Chroma retrieval pipeline and demo source citations.
3. Deterministic tax calculation for a synthetic 30,000 JOD income: the legacy result was 2,750 JOD and the Decimal result was `2750.000`.
4. Extraction of a synthetic medical receipt: 125.50 JOD, date 2026-10-14, medical category.
5. Structured JSON completion through the advisor adapter.
6. A complete, readable chat title.
7. The full advisor graph on a synthetic profile, including retrieved context, deterministic baseline/scenarios, risk review, and an action plan with no recorded pipeline errors.

Earlier attempts encountered temporary Google HTTP 503 responses, rate limits, and truncated structured output. The successful reruns are smoke checks, not a percentage-accuracy benchmark or a guarantee of provider availability.

## Changes verified

- A failed optional citation lookup no longer discards a successful deterministic calculation or routes its numeric answer to a language model.
- Citation headings preserve source identity without labeling demo fixtures as a specific official law.
- Gemini 2.5 Flash reserves its visible output budget for short titles and JSON responses, preventing thinking tokens from consuming those small response budgets. Other models and ordinary longer text responses retain their existing behavior.
- Regression checks cover retrieval failure, demo citation labels, and the Google SDK configuration used for bounded responses.

## Reproduce

```bash
cd backend
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen pytest -q tests/test_tax_engine.py tests/test_s07_decimal.py tests/test_s07_legacy_golden.py
```

For the five PostgreSQL checks, migrate an isolated PostgreSQL 17 database to Alembic head and set `S03_POSTGRES_URL`, `S04_POSTGRES_URL`, `S05_POSTGRES_URL`, `S07_POSTGRES_URL`, and `S08_POSTGRES_URL` to its SQLAlchemy async URL before running pytest. Without those variables, these checks skip.

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
```

Live checks need a Google API key configured locally and an ingested demo knowledge base. Credentials and generated local vector-store files are excluded from version control.
