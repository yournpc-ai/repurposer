# Repurposer

Automatically transform raw speech materials (video, audio, transcripts, slides, photos) into short-form videos, social media copy, quote cards, and multilingual versions for multi-platform distribution.

## Core Capabilities

- **Vertical Videos**: Speaker footage → cropped segments with burned-in subtitles; **works even without footage** — pure audio / images / slides can be turned into audiograms or still-frame videos.
- **Multiple Outputs**: Highlight clips, eye-catching hooks / headlines, LinkedIn long-form posts, quote cards, **carousel long images**, multilingual summaries, blog posts.
- **Multilingual**: Subtitle translation + **voice-cloned dubbing** (using the speaker's own voice via MiniMax voice_clone + T2A).
- **Brand Templates**: Multiple CRUD templates + default seeds; logo / CTA / subtitle style / intro-outro / music / layout and **text drag-and-drop positioning** baked into the final video; brand page uses a real `<Player>` for WYSIWYG preview.
- **AI Understanding**: M3 vision reads images (slides / charts → key points); ASR word-level subtitles; homepage prompt acts as **intent** driving all outputs.
- **Speaker = Persisted Memory**: User-selectable / auto-created profile records, extracting tone, style, and preferences from task inputs for cross-task reuse; user-isolated, supports multiple Speakers (see ADR-021).

## Core Usage Flow

The main entry point is the homepage input box, not the project list:

1. The user drops files (video / audio / transcript / slides / images) or pastes text on the homepage, and enters the desired output intent.
2. One-click creation of Project, upload of Asset, and trigger of Generation from the homepage.
3. Worker processes asynchronously: ASR transcription / text extraction / vision reading.
4. Generation runs: Analyzer splits content → Script / LinkedIn / Quote Card / Carousel / Summary / Blog and other agents generate results.
5. The user enters the project detail page to review generated clips and derivative content.
6. The user triggers rendering, and the Worker calls Remotion to generate MP4.
7. The user exports copy, images, or videos.

Speaker and Brand template are selected from the toolbar below the homepage input box; neither is mandatory.

- **Backend**: FastAPI + Python (includes queue worker)
- **Core Model**: MiniMax M3 (multimodal: text + vision reading + voice clone / T2A)
- **Frontend**: TanStack Start + TypeScript
- **Video Rendering**: Remotion (`apps/render`, Node service, clip-spec → MP4+SRT)
- **Speech Recognition**: faster-whisper (self-hosted, word-level timestamps)
- **Task Queue**: Postgres (`FOR UPDATE SKIP LOCKED`) + standalone worker, no Redis
- **Package Management**: Backend uses `uv`; frontend / render / shared components use `pnpm` workspace (`web` / `render` / `clip`)
- **Database**: PostgreSQL
- **File Storage**: Local filesystem under `assets/`; user-scoped layout (`assets/{user_id}/uploads/projects/{id}/...` and `assets/{user_id}/outputs/projects/{id}/...`). Demo assets live under `assets/demo/`. Object storage deferred until scale.
- **Local Orchestration**: `scripts/dev.sh`
- **Deployment**: Docker Compose

## Directory Structure

```
repurposer/
├── apps/
│   ├── api/                 # FastAPI backend (queue worker / ASR)
│   │   └── migrations/      # Alembic database migrations
│   ├── web/                 # TanStack Start frontend (includes vertical video editor)
│   └── render/              # Remotion rendering service (clip-spec → MP4+SRT, Node)
├── packages/
│   └── clip/                # Shared Remotion <Clip> component (web preview + render output, parity guaranteed)
├── docs/                    # Project documentation
│   ├── PRD.md              # Product Requirements Document
│   ├── ARCHITECTURE.md     # Architecture Design
│   ├── VIDEO_EDITOR.md     # Vertical Video Editor Design
│   ├── DECISIONS.md        # Architecture Decision Records
│   ├── DATABASE_MIGRATIONS.md  # Database Migration Guide
│   └── tasks/              # Deliverable task cards (e.g. voice-sample-input.md)
├── scripts/
│   └── dev.sh              # One-command local startup
├── pnpm-workspace.yaml     # web/render/clip workspace (api uses uv independently, not in workspace)
├── docker-compose.yml
└── README.md
```

## Quick Start

### 1. Install Dependencies

This project uses [`uv`](https://github.com/astral-sh/uv) for Python dependency management and [`pnpm`](https://pnpm.io/) for Node dependency management.

**Why these two:**
- **uv**: A Rust-based Python package manager, 10–100× faster than `pip`/`venv`, automatically manages virtual environments and Python versions; `uv sync` reproduces dependencies exactly from the lockfile.
- **pnpm**: Uses hard links to share a global cache, installs faster, uses less disk space, and provides stricter dependency isolation, avoiding npm's "phantom dependency" problem.

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
# Edit .env and fill in MINIMAX_API_KEY, etc.
```

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
Once started, open 👉 **http://localhost:3000** in your browser.

| Service | URL |
|---------|-----|
| Frontend (Web App) | http://localhost:3000 |
| Backend (API) | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Render Service (Remotion) | http://localhost:3001 |

> The render service (`apps/render`) is a black box called by the API worker (clip-spec → MP4+SRT); pure text output flows do not need it.

### 5. (Optional) Full-Stack Docker One-Command Run

No need to install Node / Python locally; run the full stack **db + api + worker + render + web** directly with Docker:

```bash
MINIMAX_API_KEY=sk-xxx docker compose up --build
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
- Inter-container hostnames: `API_PUBLIC_URL=http://api:8000`, `RENDER_URL=http://render:3001/render` (render pulls source video via HTTP, writes rendered output to shared volume `./assets`).
- The `render` image includes system libraries for headless Chromium; the Chromium binary (~90MB) is downloaded **lazily on first render** (no external network dependency at build time, better for CI / restricted networks).
- `web` currently uses `vite preview` for SSR, suitable for MVP / staging; for high-traffic deployments, switch to a lightweight Node adapter around the exported fetch handler (see ADR-018).

### 6. Production Reverse Proxy (nginx)

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

## Demo Project

The app seeds a demo project on startup so first-time visitors can see a fully populated results page without uploading their own media.

- **Demo project id**: `11111111-1111-1111-1111-111111111111`
- **Demo user**: the seeded default user (`DEFAULT_USER_ID`)
- **Demo video**: the object `demo/uploads/demo_talk.mp4` in the configured object-storage bucket (TOS). The seed runs ASR on it and generates **5 clips only** (no derivatives).
- The demo project is idempotent — startups are no-ops once clips exist.

To swap the demo video on an environment:

1. Replace the object `demo/uploads/demo_talk.mp4` in the bucket (e.g. via `scripts/migrate_to_tos.py --force`).
2. Run `python scripts/seed_demo.py --force` — it deletes the existing demo clips, workflow runs, **and the demo Asset row**, so ASR re-runs on the new video and 5 fresh clips are generated.

## Tests

```bash
# Backend tests (inside apps/api)
cd apps/api
uv run pytest tests/ -q

# Frontend tests (inside apps/web)
cd apps/web
pnpm test
```

## Documentation

- [Product Requirements Document](./docs/PRD.md)
- [Architecture Design](./docs/ARCHITECTURE.md)
- [API Specification](./docs/API.md)
- [Architecture Decision Records](./docs/DECISIONS.md)
- [Development Schedule & Roadmap](./docs/SCHEDULE.md)

## Development Conventions

- Backend code lives in `apps/api/`
- Frontend code lives in `apps/web/` (TanStack Start)
- Video render service lives in `apps/render/` (Remotion, Node); shared `<Clip>` component lives in `packages/clip/`
- Documentation lives in `docs/`
- Use a lightweight **pnpm workspace** to wire together `web` / `render` / `clip` (shared Remotion components guarantee "preview = rendered output"); **do not introduce heavy monorepo tools like Turborepo / Nx**. `apps/api` uses `uv` independently and is not in the workspace
- Frontend and backend communicate via REST API; types are generated from the backend OpenAPI spec
