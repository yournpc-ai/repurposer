# Database Migration Guide

> Status: Active
> Last updated: 2026-07-20

The Repurposer backend uses [SQLAlchemy 2.0](https://www.sqlalchemy.org/) as the ORM and [Alembic](https://alembic.sqlalchemy.org/) as the database migration tool.

## Why Alembic

SQLAlchemy's `Base.metadata.create_all()` can only create tables when the database is empty; **it cannot safely modify existing columns, constraints, or types**. As the project evolves, adding columns to existing tables, changing nullable flags, and adding indexes are routine tasks. Alembic is the officially maintained migration tool for SQLAlchemy. It can:

- Record version history for every schema change
- Support both upgrades and downgrades
- Auto-generate migration scripts (`autogenerate`), reducing hand-written SQL
- Explicitly control database versions in CI/CD

## Environment Setup

Make sure PostgreSQL is running (local development usually starts it automatically via `docker compose up -d db` or `./scripts/dev.sh`), and that `DATABASE_URL` in `apps/api/.env` is configured correctly.

## Common Commands

All commands are run inside the `apps/api` directory:

```bash
cd apps/api
```

### Apply migrations to the latest version

```bash
uv run alembic upgrade head
```

### Check the current database version

```bash
uv run alembic current
```

### Generate a new auto-migration

After modifying `app/models/tables.py` or `app/models/schemas.py`:

```bash
uv run alembic revision --autogenerate -m "describe your change"
```

The generated script will be placed in the `migrations/versions/` directory. **Always review it manually** after generation — autogenerate may not be fully accurate for complex constraints, enum renames, default values, and similar scenarios.

### Roll back a migration

```bash
# Roll back one step
uv run alembic downgrade -1

# Roll back to the initial state
uv run alembic downgrade base
```

### View migration history

```bash
uv run alembic history
```

## Automatic Migrations (on Application Startup)

`init_db()` in `app/models/database.py` is called during the FastAPI lifespan:

```python
command.upgrade(alembic_cfg, "head")
```

In addition, `./scripts/dev.sh` explicitly runs the following before starting the API:

```bash
uv run alembic upgrade head
```

This means that during daily local development, the database is automatically synchronized to the latest version when `./scripts/dev.sh` starts.

However, explicit migration is recommended in the following scenarios:

- First run on a new machine or new database
- CI/CD deployment pipelines
- Production environments (avoid relying on implicit migrations during application startup)

## Important Conventions

1. **Do not modify the database manually**: All schema changes must go through Alembic migration scripts.
2. **Commit migration scripts**: `migrations/versions/*.py` is part of the codebase and must be committed to git.
3. **Manually review autogenerate output**: Open the generated script and verify that it accurately expresses your intent.
4. **Model imports**: `migrations/env.py` already imports `app.models.tables`, ensuring autogenerate can detect all models.
5. **Sync vs async drivers**: The main application uses `postgresql+asyncpg`, while Alembic uses `postgresql+psycopg2`. `env.py` automatically converts the URL.

## Common Issues

### "Can't locate revision identified by xxxx" on startup

This usually happens because the version recorded in the local `alembic_version` table does not match the `migrations/versions/` directory. Solutions:

```bash
# If the database is empty or can be rebuilt
uv run alembic downgrade base
uv run alembic upgrade head

# If only the version record is out of sync, you can fix it manually
uv run alembic stamp head
```

### autogenerate does not detect changes

Check whether `migrations/env.py` correctly imports the module containing the model definitions. This project already imports `app.models.tables`.

### Rebuilding the local database from scratch

```bash
# Caution: this will delete all data
uv run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings
from app.models.database import Base
import app.models.tables  # noqa: F401 — required, registers tables on Base.metadata

async def reset():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

asyncio.run(reset())
"
# drop_all does NOT drop alembic_version (it is not in Base.metadata), so reset
# the recorded revision first — otherwise upgrade head applies nothing.
uv run alembic stamp base
uv run alembic upgrade head
```

**Pitfalls**: without `import app.models.tables`, `Base.metadata` is empty and `drop_all` silently drops nothing; without `alembic stamp base`, the surviving `alembic_version` row makes `upgrade head` a no-op and the schema stays missing.

**Never do this in production.**
