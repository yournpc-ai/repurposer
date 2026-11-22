# Repurposer

Repurposer is a chat-first AI video editor. Give it footage and a goal. The agent inspects the material, edits a persistent composition, plays the affected range and uses what it observed to revise the work. A subsequent message can refer to the same clip, frame or delivered version.

Native Tools operate on tracks, clips, objects and animations. Each edit goes through `apply_composition_edits` and saves an immutable CompositionVersion. Skills provide optional creative methods. A Motion Block can use the existing Generator implementation for complex visuals. Its declared inputs and outer clip remain addressable; individual pixels in baked media have no independent object identity.

Chat shows actual tool activity, questions, previews and deliveries. Ask for clarification when a decision blocks progress. Media generation and formal export use the account's permissions and quote. A worker returns the result to the original opening. Delivery points to the reviewed Output; older versions remain playable.

The API and worker live in `apps/api`, the web client in `apps/web`, and the renderer in `apps/render`. The player and renderer share `packages/video-spec` and `packages/video-remotion`.

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
# Backend (from the repository root)
(cd apps/api && uv sync)

# Frontend + render service + shared components (pnpm workspace; run once from repo root)
pnpm install
```

> `pnpm install` run from the root installs the web and render apps and shared video packages in one go.
> On first startup, the render service will download a headless Chromium (a few hundred MB); this is normal.

### 2. Configure Environment Variables

```bash
test -e .env || cp .env.example .env
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

From `apps/api`, run `uv run alembic current` and `uv run alembic heads`. Select the intended database before running `uv run alembic upgrade head`. Review intervening migrations and back up a populated database first. The launcher, API and worker check the installed revision. See the [migration guide](docs/DATABASE_MIGRATIONS.md).

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

> The render service (`apps/render`) is a black box called by the API worker (video-spec → media); formal export uses the saved version and its fixed sources.

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

- Both `render` and `web` depend on the workspace package `@repurposer/video-remotion`; the build context is the **repo root** (not their individual subdirectories).
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

Run the applicable checks in `CLAUDE.md`; everything run must be green before deployment:

1. **Core API/DB tests**: `cd apps/api && uv run --extra dev python -m pytest test/core -q`. These use no real model or paid production; transactional tests use disposable PostgreSQL databases.
2. **Real user journeys**: `cd apps/api && uv run python test/journeys/chat.py`, or `--only <name>[,<name>]` for a subset of the current `JOURNEYS` registry. They require a live API, current migrations, a fresh dev worker and provider quota. Journeys that produce media need separate authorization.
3. **Web suites**: `cd apps/web && pnpm test`, plus the applicable TypeScript checks.

Journey assertions lock user-visible results and server/database facts, not LLM wording or client-only DOM behavior. Browser interaction, final audiovisual quality, production rollout and publishing remain separate acceptance layers; an old green run is not current-HEAD evidence.

## Documentation

Start with the [agent architecture contract](docs/tasks/new-agent.md), [current milestones](docs/PROGRESS.md), [I8 implementation and evidence](docs/tasks/i8.md) and [domain index](docs/README.md).
