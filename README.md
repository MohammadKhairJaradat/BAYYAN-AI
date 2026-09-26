# BAYYAN AI | بيان

BAYYAN AI is a graduation project built by a student team to help individual taxpayers in Jordan organize information for an annual tax review. Users can complete a tax profile, upload supporting documents, review suggested data, explore scenarios, and ask an AI assistant for explanations. Tax estimates are calculated by Python code; AI does not decide the final numbers.

This is an educational prototype. It does not file tax returns or replace advice from a qualified professional. The bundled legal knowledge is demo material, so users should verify current rules with official sources. The original team work remains credited as described in [provenance](docs/provenance.md).

## Features

- Arabic-first interface with profile guidance and document review.
- Deterministic tax calculations and saved calculation runs.
- Document extraction, chat, and an advisor workflow when an AI provider is configured.
- Subscription tiers for testing feature limits; no payment system.
- Admin tools, automated tests, and a local development launcher.

## Technology

| Part | Tools |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Data | PostgreSQL, MinIO, ChromaDB |
| AI | Optional Gemini, Claude, OpenAI, or Groq APIs; local multilingual embeddings |
| Local services | Docker Compose |

## Requirements

- Git and Docker Desktop with a running Linux engine (WSL 2 on Windows).
- Python **3.14.6** and [uv](https://docs.astral.sh/uv/).
- Node.js **20+** and npm.
- About **10 GB** of free space for the first backend install and optional embedding model download.
- An API key is optional for basic profile and calculation flows; configure one to try AI features.

## Run locally on Windows

```powershell
git clone https://github.com/MohammadKhairJaradat/BAYYAN-AI.git
cd BAYYAN-AI
.\start.ps1 -Open
```

The launcher starts PostgreSQL and MinIO, installs dependencies, creates local environment files from the examples, applies database migrations, and starts the backend and frontend. Open **http://127.0.0.1:5173**; API documentation is at **http://127.0.0.1:8000/docs**. Stop the local app with `.\stop.ps1`.

To enable AI features, add your own provider key to `backend/.env` and restart the backend. Keep real keys out of Git. See [backend/.env.example](backend/.env.example) for available settings. Never use the example passwords or keys for a public deployment.

## Manual setup

On macOS/Linux, or to run each part separately:

```bash
docker compose up -d --wait
cd backend
cp .env.example .env
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000
```

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Set a unique `SECRET_KEY` in `backend/.env` for your local instance. The frontend reads `VITE_API_URL` from `frontend/.env.local` (the example points to port 8000).

## Check the project

```bash
cd backend && uv run pytest -q
cd ../frontend && npm run lint && npm test -- --run && npm run build
```

The project is organized into `backend/`, `frontend/`, `infra/`, and `docs/`. Database changes live in `backend/alembic/versions/`. The raw `Data/` corpus, local uploads, environment files, and generated results are intentionally excluded from Git.

## Credits and license

BAYYAN began as a **team graduation project**; this repository includes later improvements while preserving the team's original work. See [docs/provenance.md](docs/provenance.md) for publication and source notes. The existing [GPL-3.0 license](LICENSE) is retained.
