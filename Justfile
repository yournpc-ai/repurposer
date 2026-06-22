# Repurposer development commands

dev:
    ./scripts/dev.sh

setup-backend:
    cd apps/api && uv sync

setup-frontend:
    cd apps/web && pnpm install

setup: setup-backend setup-frontend
    cp .env.example .env
    mkdir -p data/uploads data/outputs

lint-backend:
    cd apps/api && uv run ruff check .

lint-frontend:
    cd apps/web && pnpm lint

typecheck-backend:
    cd apps/api && uv run mypy .

typecheck-frontend:
    cd apps/web && pnpm typecheck

test-backend:
    cd apps/api && uv run pytest

db-up:
    docker compose up -d db

db-down:
    docker compose down

clean:
    rm -rf apps/api/.venv apps/web/node_modules data/uploads/* data/outputs/*
