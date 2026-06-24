#!/bin/bash
# Dev launcher: starts Postgres (if needed), the API, and the web app.
# Deliberately avoids `set -e` so one service failing doesn't kill the rest,
# and never blocks on an unresponsive Docker daemon.

echo "Starting Repurposer development environment..."

# Always run relative to the repo root, regardless of where this is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "Cannot cd to repo root ($ROOT)"; exit 1; }

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
      postgres:16-alpine 2>/dev/null \
      || docker start repurposer-db 2>/dev/null \
      || echo "Could not start Postgres container (continuing anyway)."
  fi
else
  echo "Docker is unavailable or unresponsive — skipping Postgres startup."
  echo "  (Make sure Postgres is reachable on 5432 yourself.)"
fi

# --- backend ---------------------------------------------------------------
echo "Starting API on http://localhost:8000 ..."
( cd "$ROOT/apps/api" && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 ) &
API_PID=$!

# --- frontend --------------------------------------------------------------
echo "Starting web app on http://localhost:3000 ..."
( cd "$ROOT/apps/web" && pnpm dev ) &
WEB_PID=$!

# --- cleanup ---------------------------------------------------------------
trap 'echo; echo "Shutting down..."; kill "$API_PID" "$WEB_PID" 2>/dev/null; exit' INT TERM

wait
