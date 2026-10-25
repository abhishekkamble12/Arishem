# Arishem — working notes for Claude

Multi-tenant RAG backend (Django REST + Celery + Qdrant + Groq) with a React/TypeScript client.
Owner is a final-year B.Tech fresher; the goal is a project that is deployed, usable by strangers,
and defensible line by line in an interview.

## Layout

```
backend/
  backend/        Django project: settings.py, celery.py, urls.py, test_settings.py
  app/            models, DRF function views, permissions, throttling, tasks, metrics, tests
  Services/       agent.py (RAG query), agentic.py (decompose/critique), Extractor.py (load+chunk),
                  Ai_service/ (embedding, Qdrant), storage.py (local or S3-compatible),
                  meeting/ (Whisper + summarisation)
frontend/         Vite + React + TS + Tailwind + Zustand
evals/            golden_set.json, run_eval.py (RAGAS), SCORECARD.md
pcaps/            sample policy docs used by the eval
```

## Commands

Run from `backend/` unless noted. Windows shell is PowerShell/Git Bash; the venv is `../.venv`.

| Task | Command |
|---|---|
| Install (dev) | `pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-dev.txt` |
| Lint (repo root) | `ruff check .` |
| Test | `python manage.py test --settings=backend.test_settings` |
| Migrations up to date | `python manage.py makemigrations --check --dry-run --settings=backend.test_settings` |
| Migrate / API / worker | `python manage.py migrate` / `runserver` / `celery -A backend worker -l info` |
| Eval (repo root, needs `GROQ_API_KEY`; ragas not yet in any requirements file) | `python evals/run_eval.py` |
| Frontend (in `frontend/`) | `npm install && npm run dev` (`npm run build` type-checks then builds) |
| Full local stack | `cp .env.example .env` (set SECRET_KEY, GROQ_API_KEY) then `docker compose up --build` |

Dependencies: `backend/requirements.txt` is the single pinned source (Docker and CI use it);
`requirements-optional.txt` holds PPTX + Whisper/yt-dlp; `ruff format` is configured but not yet applied repo-wide.

## Conventions

- Python 3.12, type hints on new code, `logging` not `print`, no bare `except:`.
- Config only via `python-decouple` / env vars. Never hardcode secrets; document new vars in `backend/backend/.env.example`.
- Every workspace-scoped query MUST carry the `metadata.workspace_id` Qdrant filter (built in `Services/agent.py: query`).
- Tests must be offline: fake the vector store and the LLM. No test may need network or a real key.
- Branch `upgrade/tier1`; atomic commits; conventional commit messages (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `ci:`).
- Do not rewrite working core logic without explaining why first.

## No-overengineering rule

No microservices, Kubernetes, new frameworks or buzzword patterns unless the project demonstrably needs them.
Every change needs a one-sentence reason the owner can defend in an interview. Never invent metrics, users,
benchmarks or features: every number in docs must come from a script that can be re-run.

## Process

Work in phases (see the owner's brief). At the end of each phase run lint + tests, show the real output,
and wait for approval before starting the next. Ask rather than guess on stack, hosting and scope decisions.

## Known repo quirks

- The git repo that matters is `D:\Arishem\Arishem` (remote `abhishekkamble12/Arishem`). The parent `D:\Arishem`
  is a second repo that tracks `Arishem` as a broken gitlink (no `.gitmodules`); ignore it.
- `STORAGE_BACKEND=local|s3`; some call sites still say `s3_key` / `download_from_s3` (kept for compatibility).
- Meetings and social login are gated by `ENABLE_MEETINGS` / `ENABLE_SOCIAL_AUTH` (default off); tests turn them on.
