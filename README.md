# Repurposer

An AI agent for knowledge experts: it turns existing material — talks, meetings, podcasts, transcripts, slides, photos — into the content the user names: LinkedIn posts, articles, quote cards, carousels, vertical clips, and multi-language versions, in the expert's own voice and style.

Core channels are LinkedIn, institutional websites, and email newsletters; multi-language output (EN / FR / DE / ES / IT / ZH) is the entry ticket.

## Core Capabilities

- **Named outputs, not a fixed bundle** — the plan is built per request from a skill registry: vertical clips, LinkedIn posts, articles, quote cards, carousels, multi-language versions. The user names it, the agent makes it.
- **Vertical clips with or without footage** — speaker footage → cropped, subtitled segments; pure audio / images / slides → still-frame videos.
- **Multilingual** — subtitle translation plus voice-cloned dubbing (the speaker's own voice via MiniMax voice_clone + T2A).
- **Persona = persisted identity memory** — tone, style, taboos, voice binding, and visual skin (caption style / title / intro-outro / music) in one object; user-isolated, multi-instance, auto-created from task material when not explicitly selected (ADR-037/038). The persona page edits the skin with a live Remotion `<Player>` preview, pixel-identical to the rendered output.
- **AI understanding** — M3 vision reads slides and charts; self-hosted ASR produces word-level timestamps.
- **Chat is the single intent surface** — every request (generation, refinement, revision) goes through the project chat: the plan agent builds the task book, the user confirms, the skill DAG runs.

## Core Usage Flow

The main entry point is the home composer, not the project list:

1. The user drops files (video / audio / transcript / slides / images) or pastes text into the home composer, and writes what they want. Optional Assets / Persona blocks ride the composer's top edge; neither is mandatory.
2. Send creates the project, uploads the assets, and hands the draft to the project chat (`/projects/$id?overlay=chat`) as the first `POST /chat` message.
3. The plan agent proposes a task book (outputs, languages, clip count); the user refines it in chat and confirms — confirmation creates the run.
4. The worker processes assets asynchronously (ASR / text extraction / vision reading), then executes the skill DAG: `select_clips`, `write_post`, `write_quotes`, `write_carousel`, `write_article`, `dub_clip`, `translate_clip`, `add_music`, and friends.
5. Clips render automatically on generation — the worker claims pending `Clip` rows and calls the Remotion service; there is no manual "Render" button.
6. Outputs land on the results canvas; the user refines them through the chat dock and exports copy, images, or videos.

## Tech Stack

- **Backend**: FastAPI + Python, plus a standalone queue worker process
- **Core Model**: MiniMax M3 (multimodal: text + vision reading + voice clone / T2A)
- **Frontend**: TanStack Start + TypeScript
- **Video Rendering**: Remotion (`apps/render`, Node service, clip-spec → MP4+SRT)
- **Speech Recognition**: faster-whisper (self-hosted, word-level timestamps)
- **Task Queue**: Postgres (`FOR UPDATE SKIP LOCKED`) + standalone worker, no Redis
- **Package Management**: backend uses `uv`; frontend / render / shared components use a `pnpm` workspace (`web` / `render` / `clip`)
- **Database**: PostgreSQL
- **File Storage**: S3-compatible object storage (Volcengine TOS) for all persistent files — uploads and rendered outputs are object keys; reads are public, uploads use backend-issued presigned PUT URLs (ADR-024). No local media directories.
- **Local Orchestration**: `scripts/dev.sh`
- **Deployment**: Docker Compose

## Directory Structure

```
repurposer/
├── apps/
│   ├── api/                 # FastAPI backend (agents / skills / chat / pipeline / queue worker / ASR)
│   │   └── migrations/      # Alembic database migrations
│   ├── web/                 # TanStack Start frontend (includes vertical video editor)
│   └── render/              # Remotion rendering service (clip-spec → MP4+SRT, Node)
├── packages/
│   └── clip/                # Shared Remotion <Clip> component (web preview + render output, parity guaranteed)
├── docs/                    # Project documentation — governed index in docs/README.md
│   ├── PRD.md               # Product positioning & requirements
│   ├── PROGRESS.md          # Progress snapshot + schedule + backlog (sole source of truth for priorities)
│   ├── MODULE_ARCHITECTURE.md  # Module map, table ownership, current architecture
│   ├── DECISIONS.md         # Current ADRs
│   ├── RENDERING.md         # clip-spec field contract + render chain
│   └── tasks/               # Per-feature implementation briefs
├── scripts/
│   └── dev.sh               # One-command local startup
├── pnpm-workspace.yaml      # web/render/clip workspace (api uses uv independently, not in workspace)
├── docker-compose.yml
└── README.md
```

## Quick Start

### 1. Install Dependencies

This project uses [`uv`](https://github.com/astral-sh/uv) for Python dependency management and [`pnpm`](https://pnpm.io/) for Node dependency management.

**Why these two:**

- **uv**: a Rust-based Python package manager, 10–100× faster than `pip`/`venv`; automatically manages virtual environments and Python versions; `uv sync` reproduces dependencies exactly from the lockfile.
- **pnpm**: hard-links a global cache, installs faster, uses less disk space, and provides stricter dependency isolation, avoiding npm's "phantom dependency" problem.

**If not yet installed:**

```bash
# Install uv (macOS / Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh
# macOS via Homebrew: brew install uv
# Windows (PowerShell): powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install pnpm (requires Node.js 18+)
npm install -g pnpm
# Or standalone install script: curl -fsSL https://get.pnpm.io/install.sh | sh -
# macOS via Homebrew: brew install pnpm
```

> After installation, restart your terminal (or `source` your shell config) so `uv` / `pnpm` are available in PATH. Verify with `uv --version` and `pnpm --version`.

**Install project dependencies:**

```bash
# Backend
cd apps/api
uv sync

# Frontend + render service + shared components (pnpm workspace; run once from repo root)
pnpm install
```

> `pnpm install` run from the root installs all three workspace packages (`apps/web`, `apps/render`, `packages/clip`) in one go.
> On first startup, the render service will download a headless Chromium (a few hundred MB); this is normal.

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Fill in the two required groups in `.env`:

- `MINIMAX_API_KEY` — the multimodal model key.
- `S3_*` — object-storage credentials (`S3_ENDPOINT_URL` / `S3_BUCKET_NAME` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_PUBLIC_URL`). All user uploads and rendered outputs live here; there is no local-disk fallback.

### 3. Start the Database with Docker

The project uses PostgreSQL; running it via Docker is recommended to avoid local installation.

```bash
# Start only the database container (postgres:18-alpine, port 5432, database name repurposer)
docker compose up -d db

# Common commands
docker compose ps          # Check status
docker compose logs -f db  # View logs
docker compose stop db     # Stop
```

- Default connection string (already in `.env.example`):
  `postgresql+asyncpg://postgres:postgres@localhost:5432/repurposer`
- Data is persisted in the Docker volume `postgres_data`; `docker compose stop` does not delete data.
- Note: `./scripts/dev.sh` will automatically launch a `repurposer-db` container via Docker when port 5432 is free;
  if you already started it with `docker compose up -d db` above, the script will skip it automatically and not start a duplicate.

> If Docker is unavailable, the script will print a warning and skip; in that case, please ensure port 5432 has a connectable PostgreSQL instance.

### 4. Run Database Migrations

The backend uses [Alembic](https://alembic.sqlalchemy.org/) to manage database schema changes. Before first startup or after pulling new code, apply migrations to the latest version:

```bash
cd apps/api
uv run alembic upgrade head
```

Common commands:

```bash
# Check current migration version
uv run alembic current

# Generate a new auto-migration (run after modifying models)
uv run alembic revision --autogenerate -m "describe your change"

# Rollback one level
uv run alembic downgrade -1
```

> **Note**: `./scripts/dev.sh` automatically runs `uv run alembic upgrade head` before starting the API, so manual migrations are not required for daily local development. However, explicit execution is recommended for first-time deployment or in CI.

### 5. One-Command Startup, then visit :3000

```bash
./scripts/dev.sh
```

The script will simultaneously start the **backend (:8000)**, **queue worker**, **render service (:3001)**, and **frontend (:3000)**, and automatically start the database when needed.
Once started, open **http://localhost:3000** in your browser.

| Service | URL |
|---------|-----|
| Frontend (Web App) | http://localhost:3000 |
| Backend (API) | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Render Service (Remotion) | http://localhost:3001 |

> The render service (`apps/render`) is a black box called by the API worker (clip-spec → MP4+SRT); pure text output flows do not need it.

### 6. (Optional) Full-Stack Docker One-Command Run

No need to install Node / Python locally; run the full stack **db + api + worker + render + web** directly with Docker:

```bash
# The compose file reads .env (or shell env) — MINIMAX_API_KEY and the S3_* keys are required
docker compose up --build
# Then visit http://localhost:3000
```

Service orchestration details:

| Service | Image / Build | Description |
|---------|---------------|-------------|
| `db` | postgres:18-alpine | Database; data persisted in volume `postgres_data` |
| `api` | `apps/api/Dockerfile` (uv) | FastAPI, :8000 |
| `worker` | Same api image, `command: python -m app.worker` | Queue consumer; calls render service |
| `render` | `apps/render/Dockerfile` (build context = repo root) | Remotion render service, :3001, includes Chromium |
| `web` | `apps/web/Dockerfile` (build context = repo root) | TanStack Start SSR, :3000 |

Notes:

- Both `render` and `web` depend on the workspace package `@repurposer/clip`; the build context is the **repo root** (not their individual subdirectories).
- Inter-container hostnames: `API_PUBLIC_URL=http://api:8000`, `RENDER_URL=http://render:3001/render`. All media flows through object storage: render pulls source video over HTTP and uploads MP4/SRT results via presigned PUT URLs — there are no shared file volumes between containers.
- The `render` image includes system libraries for headless Chromium; the Chromium binary (~90MB) is downloaded **lazily on first render** (no external network dependency at build time, better for CI / restricted networks).
- `web` currently uses `vite preview` for SSR, suitable for MVP / staging; for high-traffic deployments, switch to a lightweight Node adapter around the exported fetch handler (see ADR-018).

### 7. Production Reverse Proxy (nginx)

In production the web container and api container sit behind nginx. **The `/api` prefix is owned by FastAPI alone** — nginx must forward transparently, and the web bundle must not add its own `/api`:

```nginx
# Correct: no trailing slash on proxy_pass — /api/v1/... is forwarded as-is
location /api/ {
    proxy_pass http://127.0.0.1:8000;
}
```

- Web build arg: `VITE_API_URL=https://<your-domain>` (**no trailing `/api`**; the value is inlined into the JS bundle at build time, so changing it requires `--build web`, not a restart).
- Pitfall: `proxy_pass http://127.0.0.1:8000/;` (with trailing slash) strips the `/api/` prefix. Pairing that with a bundle base that ends in `/api` produces the double-`/api/api/v1/...` URL shape — it only works while both misconfigurations stay in lockstep and breaks confusingly during partial deploys.
- Rebuild `api`/`worker`/`web` together (`docker compose up -d --build api worker web`) so new frontend bundles never call routes an old api image doesn't have.
- The api logs every request as `http_request` (method, path as received post-proxy, query, status, duration, client IP from `X-Forwarded-For`, plus redacted JSON request/response bodies) and every error with its reason (`http_error` / `http_validation_error` / `http_unhandled_error`) — the first place to check when a request behaves differently between environments.

## Tests

- **Frontend**: `cd apps/web && pnpm test` (vitest).
- **Backend**: the API test suite was removed after it drifted from the rapidly changing implementation — verify backend changes by running the relevant flow end-to-end. A few pure unit tests remain under `apps/api/tests/` (`uv run pytest tests/ -q`).

## Documentation

The governed doc index — which doc owns which truth — lives in [docs/README.md](./docs/README.md). Key docs:

- [Product Requirements](./docs/PRD.md)
- [Progress & Schedule](./docs/PROGRESS.md) — sole source of truth for priorities and the backlog
- [Module Architecture](./docs/MODULE_ARCHITECTURE.md) — module map, table ownership, current system architecture
- [Architecture Decision Records](./docs/DECISIONS.md) — current ADRs only
- [Rendering & clip-spec](./docs/RENDERING.md) — the sole render contract
- [API Specification](./docs/API.md)

## Development Conventions

- Backend code lives in `apps/api/`
- Frontend code lives in `apps/web/` (TanStack Start)
- Video render service lives in `apps/render/` (Remotion, Node); shared `<Clip>` component lives in `packages/clip/`
- Documentation lives in `docs/`
- Use a lightweight **pnpm workspace** to wire together `web` / `render` / `clip` (shared Remotion components guarantee "preview = rendered output"); **do not introduce heavy monorepo tools like Turborepo / Nx**. `apps/api` uses `uv` independently and is not in the workspace
- Frontend and backend communicate via REST API; types are generated from the backend OpenAPI spec
