# KSP Datathon 2026 — Challenge 1

Karnataka State Police — Intelligent Conversational AI & Crime Analytics
Platform. Full architecture specs live in `steering-docs/`.

## Running locally

Two servers, run in separate terminals.

### 1. Backend (FastAPI)

```bash
cd backend
cp .env.example .env   # fill in Supabase + LLM credentials — see backend/README.md
uvicorn app.main:app --reload --workers 1
```

Runs at http://localhost:8000. `--workers 1` is required — the agent's
thread store is in-process (`steering-docs/ORCHESTRATOR_STEERING.md` O-13).

Set `ASK_ENGINE=agent` in `backend/.env` to run the real orchestrator against
live data; `fixture` (the default) serves canned demo responses instead.

> If `uvicorn` fails with a "bad interpreter" error, the committed `.venv`'s
> console scripts may have a stale shebang from an earlier repo location.
> Work around it with `python -m uvicorn app.main:app --reload --workers 1`,
> or rebuild the venv.

### 2. Frontend (Next.js)

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install   # first time only
npm run dev
```

Runs at http://localhost:3000.

See `backend/README.md` and `frontend/README.md` for full setup (Supabase
migrations, demo user provisioning, mock-vs-real Ask service toggle).
