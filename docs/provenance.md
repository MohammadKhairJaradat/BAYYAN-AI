# BAYYAN source and publication inventory

This working copy is a team graduation project for individual Jordanian taxpayers. The BAYYAN / بيان identity, existing code, designs, documentation, tax fixtures, and project history remain attributable to the original team. A new local Git repository was initialized in this supplied directory on 2026-09-25 at Mohammad's request because this copy had no `.git` directory. This new repository **does not contain or replace the team's original Git history**. No commit or public release has been made by this work.

## Source and credits to resolve before public release

- Record the original repository URL or archive identifier, its authors, and the contribution credits agreed with the team. This copy alone cannot establish the original history or individual ownership. Do not invent names or imply that subsequent development created the original project.
- The root `LICENSE` is GPL-3.0 and remains unchanged. Confirm the team's agreement on attribution and the right to publish the existing code and assets under that license before making a public repository.
- Confirm provenance and redistribution rights for graphics, fonts, sample documents, knowledge-base content, diagrams, screenshots, and any external logos separately. A source file being present here is not evidence of permission to republish it.
- Prior project documentation reports previously exposed AI keys. Owners must revoke or rotate those credentials and verify status outside Git. Do not paste keys or local `.env` files into issues, commits, or this inventory.

## Initial file inventory

| Material | Current handling | Release decision |
|---|---|---|
| `backend/app`, `backend/alembic`, `backend/tests`, `frontend/src`, launch scripts | Application source and test history in this copy | Candidate source; preserve team credit and review dependency/licenses before release |
| `README.md`, `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `docs/`, `.claude/skills/` | Project and agent documentation, including historical notes | Review for sensitive details and personal data before selecting public documentation |
| `LICENSE` | Existing GPL-3.0 text | Preserve unchanged; confirm publication agreement |
| `backend/knowledge_base/` | Two demo legal-text fixtures, not an approved legal corpus | Label as synthetic/demo; review source rights and legal claims |
| `frontend/public/`, diagrams and images under `docs/` | Brand and documentation assets | Review asset ownership and redistribution permission |
| `backend/.env`, `frontend/.env.local`, any `.env.*` other than `.env.example` | Machine-specific settings and secrets | Excluded from Git; never publish |
| `TEMP_FILE/outputs/` | Local QA reports, scripts, screenshots, and generated evidence moved from root `outputs/` | Excluded from Git pending case-by-case privacy and rights review; files remain on disk |
| `TEMP_FILE/scratch/` | Local exploratory legal-text scripts and intermediate text moved from root `scratch/` | Excluded from Git; review provenance before reusing or publishing anything derived from it |
| `TEMP_FILE/.clinerules/`, `TEMP_FILE/coordination-prompts/` | Archived Cline rules and agent onboarding prompts | Excluded from Git; no application runtime dependency |
| `backend/.venv`, `frontend/node_modules`, `frontend/dist`, Python caches, Chroma runtime data, `.devstate.json`, `.claude/scheduled_tasks.lock` | Rebuildable or local state | Excluded from Git; never publish as source |
| `backend/package-lock.json` | Existing file in backend despite Python dependencies being managed by uv | Preserve for now; inspect purpose and decide whether it belongs in a release |

Before publishing, inspect `git status --short` and the proposed staged diff, run a secret scan over the selected material and any available original history, and have the team review credits and asset rights. Initialization alone is not a release approval.
