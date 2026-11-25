"""Layer 1B infrastructure contracts: API boot & Alembic migration vs Base.metadata parity."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import tables as _tables  # noqa: F401
from app.models.database import Base

API_ROOT = Path(__file__).resolve().parents[2]


def test_api_application_imports():
    """The API composition root must import cleanly and publish core Chat-Origin routes."""
    from app.main import app

    assert app.title
    paths = set(app.openapi()["paths"].keys())
    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/conversations/{conversation_id}/compact" in paths
    assert "/api/v1/chat/messages/{message_id}/feedback" in paths
    assert "/api/v1/projects/{project_id}/workbench" in paths
    assert "/api/v1/skills/{skill_version_id}/slot-preview" in paths


def test_alembic_single_head_and_schema_matches_models(monkeypatch):
    """Alembic ``upgrade head`` on a fresh DB must match ``Base.metadata`` tables & columns."""
    cfg = AlembicConfig(str(API_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected a single Alembic head, got {heads}"

    db_name = f"rep_alembic_parity_{uuid4().hex[:10]}"
    async_server = settings.database_url.rsplit("/", 1)[0]
    sync_server = async_server.replace("postgresql+asyncpg", "postgresql+psycopg2")
    admin = create_engine(f"{sync_server}/postgres", isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    monkeypatch.setattr(settings, "database_url", f"{async_server}/{db_name}")
    check_engine = create_engine(f"{sync_server}/{db_name}", poolclass=NullPool)
    try:
        alembic_command.upgrade(cfg, "head")
        alembic_command.downgrade(cfg, "-1")
        previous_columns = {c["name"] for c in inspect(check_engine).get_columns("sound_effects")}
        assert "domain" in previous_columns and "waveform_peaks" not in previous_columns
        from app.catalog.sfx_ingest import analyze_audio

        measured = analyze_audio((API_ROOT / "assets/sfx/switch.wav").read_bytes())
        with check_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO sound_effects
                    (id, slug, engine_kind, name, category, summary, duration_ms, content_sha256, created_at, updated_at)
                VALUES (:id, 'foley_switch', 'sample', 'Switch', 'toggle', 'Switch', 385, :digest, now(), now())
            """), {"id": uuid4(), "digest": measured["content_sha256"]})
        alembic_command.upgrade(cfg, "head")
        insp = inspect(check_engine)
        peaks = next(c for c in insp.get_columns("sound_effects") if c["name"] == "waveform_peaks")
        assert str(peaks["type"]) == "JSONB" and not peaks["nullable"]
        assert peaks["default"] == "'[]'::jsonb"
        with check_engine.connect() as conn:
            assert conn.scalar(text("SELECT waveform_peaks FROM sound_effects WHERE slug = 'foley_switch'")) == measured["waveform_peaks"]
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == heads[0]
        migrated_tables = set(insp.get_table_names()) - {"alembic_version"}
        model_tables = set(Base.metadata.tables.keys())
        assert migrated_tables == model_tables, (
            f"Table drift between Alembic and tables.py: "
            f"only_in_alembic={sorted(migrated_tables - model_tables)}, "
            f"only_in_models={sorted(model_tables - migrated_tables)}"
        )

        column_drift: dict[str, dict[str, list[str]]] = {}
        for table_name in sorted(model_tables):
            migrated_cols = {c["name"] for c in insp.get_columns(table_name)}
            model_cols = set(Base.metadata.tables[table_name].columns.keys())
            if migrated_cols != model_cols:
                column_drift[table_name] = {
                    "only_in_alembic": sorted(migrated_cols - model_cols),
                    "only_in_models": sorted(model_cols - migrated_cols),
                }
        assert not column_drift, f"Column drift between Alembic and tables.py: {column_drift}"
    finally:
        check_engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
        admin.dispose()
