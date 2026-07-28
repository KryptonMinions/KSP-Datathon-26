# KSP Datathon 2026 — Challenge 1

Karnataka State Police — Intelligent Conversational AI & Crime Analytics
Platform. Full architecture specs live in `steering-docs/`.

## Directory structure

```
backend/             FastAPI service — auth, /ask orchestrator agent, voice
                      intake, PDF export. See backend/README.md.
frontend/             Next.js app (dashboard, cases, ask, admin). See
                      frontend/README.md.
embeddings-service/   Standalone microservice serving multilingual-e5-base
                      embeddings for RAG retrieval. See
                      embeddings-service/README.md.
db/                   Hand-authored SQL migrations + curated reference CSVs.
                      See db/README.md.
dataset/              Raw, read-only source data (boundaries, station maps,
                      BNS/IPC PDFs) the seed pipeline builds from. See
                      dataset/README.md.
scripts/seed/         Seeding pipeline: normalizes dataset/ → loads db/
                      migrations → populates Supabase with reference data,
                      golden demo threads, Kannada translations, and
                      embeddings. Order and details in db/README.md.
steering-docs/        Architecture and design specs (auth, orchestrator,
                      semantic layer, data schema, demo scenarios, etc.) —
                      the source of truth for how the system is supposed to
                      behave.
References/           Datathon challenge brief PDFs (data discovery, demo
                      script, evaluation criteria, semantic layer, trust
                      design).
client/               Unused default Catalyst client scaffold, superseded by
                      frontend/out (the actual deployed static export).
catalyst.json, .catalystrc   Zoho Catalyst deployment config (see
                      Deployment below).
```

## Running locally

Three servers, run in separate terminals. Start the embeddings service
before the backend if you're running `ASK_ENGINE=agent` — the agent's
`search_narratives` tool calls it at query time.

### 1. Embeddings service

```bash
cd embeddings-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set EMBEDDINGS_API_KEY to match backend/.env, or leave blank for local dev
uvicorn app.main:app --reload --port 8081
```

Runs at http://localhost:8081. First request downloads the embedding model
from Hugging Face (~450MB) and caches it. See `embeddings-service/README.md`.

### 2. Backend (FastAPI)

```bash
cd backend
cp .env.example .env   # fill in Supabase + LLM credentials — see backend/README.md
uvicorn app.main:app --reload --workers 1
```

Runs at http://localhost:8000. `--workers 1` is required — the agent's
thread store is in-process (`steering-docs/ORCHESTRATOR_STEERING.md` O-13).

Set `ASK_ENGINE=agent` in `backend/.env` to run the real orchestrator against
live data (needs the embeddings service above and working LLM credentials);
`fixture` (the default) serves canned demo responses instead. Point
`EMBEDDINGS_BASE_URL` at `http://localhost:8081/v1` when running the agent
engine locally.

> If `uvicorn` fails with a "bad interpreter" error, the committed `.venv`'s
> console scripts may have a stale shebang from an earlier repo location.
> Work around it with `python -m uvicorn app.main:app --reload --workers 1`,
> or rebuild the venv.

### 3. Frontend (Next.js)

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install   # first time only
npm run dev
```

Runs at http://localhost:3000.

See `backend/README.md`, `frontend/README.md`, and
`embeddings-service/README.md` for full setup (Supabase migrations, demo
user provisioning, mock-vs-real Ask service toggle).

### Demo credentials

For evaluators — accounts seeded by `backend/scripts/demo_users.json` via
`backend/scripts/provision_users.py`:

| Username         | Password      | Role                   | Officer ID   |
| ---------------- | ------------- | ---------------------- | ------------ |
| `io.demo`         | `I0_ER`       | investigating_officer  | KSP-23417    |
| `supervisor.demo` | `$upervis0r`  | supervisor              | KSP-70068    |
| `analyst.demo`    | `An@lyst`     | analyst                 | KSP-87128    |
| `admin.demo`      | `@dmin`       | admin                   | —            |

### Database

The backend and agent expect a Supabase Postgres instance with the schema in
`db/migrations/` applied and seeded via `scripts/seed/` (reference data,
golden demo threads, Kannada translations, and embeddings). See
`db/README.md` for the migration list and full seeding order, and
`dataset/README.md` for what raw source data feeds into it.

## Deployment

The backend and embeddings service deploy as separate Docker containers to
Zoho Catalyst AppSail; the frontend deploys as a Catalyst static client from
its Next.js static export (`frontend/out`). `catalyst.json` declares both;
`backend/Dockerfile` and `embeddings-service/Dockerfile` both bind to the
port Catalyst injects via `X_ZOHO_CATALYST_LISTEN_PORT` (falling back to
8080 for local `docker run`). Production env vars (Supabase, LLM profiles,
Catalyst OAuth/cache/Stratus settings) are configured per-environment in
Catalyst, not committed to the repo — `backend/app-config.json` (gitignored)
holds the local copy used for deploys.

### Frontend on Vercel (alternative to the Catalyst client)

The frontend can also deploy to Vercel instead of (or alongside) the
Catalyst static client — same Next.js static export (`output: "export"` in
`frontend/next.config.ts`), no code changes needed for that part. Vercel
auto-detects the Next.js framework and serves the export directly.

1. **Import the repo in Vercel** and set **Root Directory** to `frontend` in
   the project's General settings — this is a monorepo, so Vercel needs to
   know the Next.js app isn't at the repo root. Build/output settings can be
   left on the Next.js framework defaults.
2. **Environment variables** (Project Settings → Environment Variables, set
   for Production and Preview):
   - No backend is deployed yet, so run the frontend standalone against its
     fixture data: set `NEXT_PUBLIC_ASK_SERVICE=mock`. Leave
     `NEXT_PUBLIC_API_URL` unset in this mode — auth, voice, and export calls
     fall back to `http://localhost:8000`, which won't resolve on Vercel, so
     those features won't work until a real backend URL is added (see
     `frontend/README.md` for the mock-vs-real toggle).
   - Once a backend is deployed (Catalyst AppSail or elsewhere), set
     `NEXT_PUBLIC_API_URL` to its public URL and remove
     `NEXT_PUBLIC_ASK_SERVICE` (or set it to unset/`real`) to switch the Ask
     page to live data.
3. **Backend CORS**, once a real backend is wired up: set the backend's
   `FRONTEND_ORIGIN` env var to include the Vercel domain, comma-separated
   alongside any other origins that need access, e.g.
   `FRONTEND_ORIGIN=http://localhost:3000,https://your-app.vercel.app`
   (`backend/app/config.py` splits this into a list for
   `CORSMiddleware.allow_origins`). Without this, the browser will block
   every request from the Vercel-hosted frontend with a CORS error.
