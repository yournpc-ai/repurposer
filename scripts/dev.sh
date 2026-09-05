#!/bin/bash
# Dev launcher: starts Postgres (if needed), the API, and the web app.
# Deliberately avoids `set -e` so one service failing doesn't kill the rest,
# and never blocks on an unresponsive Docker daemon.

echo "Starting Repurposer development environment..."

# Always run relative to the repo root, regardless of where this is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "Cannot cd to repo root ($ROOT)"; exit 1; }

export DEMO_SEED_ASYNC=true

# --- helpers ---------------------------------------------------------------
kill_port() {
  local port=$1 name=$2 pids
  pids=$(lsof -ti :"$port" 2>/dev/null)
  if [ -n "$pids" ]; then
    echo "Killing existing $name on port $port..."
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null
  fi
}

# Run a command with a timeout, even without coreutils' `timeout`.
with_timeout() {
  local secs=$1; shift
  "$@" &
  local cmd_pid=$!
  ( sleep "$secs"; kill -9 "$cmd_pid" 2>/dev/null ) &
  local killer=$!
  if wait "$cmd_pid" 2>/dev/null; then
    kill "$killer" 2>/dev/null
    return 0
  fi
  return 1
}

port_in_use() { lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# Wait until a URL returns HTTP 200, up to a timeout.
wait_for_url() {
  local url=$1 name=$2 timeout=${3:-30}
  echo "Waiting for $name to be ready..."
  for ((i=0; i<timeout; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready."
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $name (continuing anyway)."
  return 1
}

# --- free the dev ports ----------------------------------------------------
kill_port 8000 "backend"
kill_port 3000 "frontend"

# --- PostgreSQL ------------------------------------------------------------
if port_in_use 5432; then
  echo "PostgreSQL already running on 5432, skipping Docker."
elif with_timeout 5 docker ps >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q repurposer-db; then
    echo "Starting PostgreSQL (Docker)..."
    docker run -d --name repurposer-db \
      -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres \
      -e POSTGRES_DB=repurposer \
      -p 5432:5432 \
      postgres:18-alpine 2>/dev/null \
      || docker start repurposer-db 2>/dev/null \
      || echo "Could not start Postgres container (continuing anyway)."
  fi
else
  echo "Docker is unavailable or unresponsive — skipping Postgres startup."
  echo "  (Make sure Postgres is reachable on 5432 yourself.)"
fi

# --- database migrations ---------------------------------------------------
# Apply Alembic migrations before starting the API so schema issues surface
# immediately rather than inside the FastAPI lifespan.
if port_in_use 5432 || with_timeout 5 docker ps >/dev/null 2>&1; then
  echo "Applying database migrations..."
  ( cd "$ROOT/apps/api" && uv run alembic upgrade head ) || echo "Migration step exited (continuing anyway)."
else
  echo "Postgres does not appear to be available — skipping migrations."
fi

# --- backend ---------------------------------------------------------------
echo "Starting API on http://localhost:8000 ..."
( cd "$ROOT/apps/api" && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 ) &
API_PID=$!

# --- worker ----------------------------------------------------------------
# Processes the Postgres-backed job queue (asset processing + generation) in a
# separate process so heavy jobs don't compete with the API's online requests.
echo "Starting background worker ..."
( cd "$ROOT/apps/api" && uv run python -m app.worker ) &
WORKER_PID=$!

# Wait for the API to finish startup before launching the frontend, otherwise
# the first page fetch races the FastAPI application lifespan.
wait_for_url "http://localhost:8000/health" "API" 60

# --- render service --------------------------------------------------------
# Remotion render service (clip-spec -> MP4+SRT). Node/pnpm, headless Chrome +
# bundled FFmpeg. Black box the api worker calls; not needed for text-only flows.
#
# Proxy: the direct link from a dev machine to TOS is throttled, and the
# service's source staging + result upload are proxy-aware via HTTPS_PROXY
# (loopback exempt). When the local proxy is listening, carry the env into
# the render service so large-media transfers don't die on undici timeouts
# (2026-08-19: a hand restart without the env reproduced exactly that — the
# render SUCCEEDS and only the PUT upload times out).
echo "Starting render service on http://localhost:3001 ..."
if nc -z 127.0.0.1 6152 2>/dev/null; then
  ( cd "$ROOT/apps/render" && HTTPS_PROXY="http://127.0.0.1:6152" HTTP_PROXY="http://127.0.0.1:6152" pnpm dev ) &
else
  ( cd "$ROOT/apps/render" && pnpm dev ) &
fi
RENDER_PID=$!

# --- frontend --------------------------------------------------------------
echo "Starting web app on http://localhost:3000 ..."
( cd "$ROOT/apps/web" && pnpm dev ) &
WEB_PID=$!

# --- startup liveness gate ---------------------------------------------------
# 2026-09-06 lesson: the worker died seconds after launch (an unguarded
# startup exception) and nothing said so — its traceback scrolled by under
# the other services' logs and a user's run queued forever. The API has
# wait_for_url; the other three had NOTHING. Give every service a few
# seconds to prove it's alive, then SAY the verdict per service.
check_alive() {
  local pid=$1 name=$2 hint=$3
  if kill -0 "$pid" 2>/dev/null; then
    echo "  ✔ $name (pid $pid)"
    return 0
  fi
  echo "  ✘ $name DIED AT STARTUP — its traceback is above."
  echo "    rerun: $hint"
  return 1
}

sleep 5
echo "Service status:"
DEAD=0
check_alive "$API_PID"    "API    http://localhost:8000"  "( cd apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 )" || DEAD=1
check_alive "$WORKER_PID" "worker (job queue)"            "( cd apps/api && uv run python -m app.worker )"                                   || DEAD=1
check_alive "$RENDER_PID" "render http://localhost:3001"  "( cd apps/render && pnpm dev )"                                                   || DEAD=1
check_alive "$WEB_PID"    "web    http://localhost:3000"  "( cd apps/web && pnpm dev )"                                                      || DEAD=1
if [ "$DEAD" -ne 0 ]; then
  echo "⚠ One or more services failed to start — the environment is NOT whole."
fi

# --- cleanup ---------------------------------------------------------------
trap 'echo; echo "Shutting down..."; kill "$API_PID" "$WORKER_PID" "$RENDER_PID" "$WEB_PID" 2>/dev/null; exit' INT TERM

wait
