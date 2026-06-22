#!/bin/bash
set -e

echo "Starting Repurposer development environment..."

# Start PostgreSQL if not running
if ! docker ps | grep -q repurposer-db; then
  echo "Starting PostgreSQL..."
  docker run -d --name repurposer-db \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=repurposer \
    -p 5432:5432 \
    postgres:16-alpine 2>/dev/null || true
fi

# Start backend
cd apps/api
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

# Start frontend
cd ../web
pnpm dev &
WEB_PID=$!

# Cleanup on exit
trap "kill $API_PID $WEB_PID; exit" INT TERM

wait
