"""Shared PostgreSQL, ASGI Chat client, and scripted LLM helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from importlib import import_module
from inspect import isawaitable
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import settings

from app.dependencies import get_current_user_required, get_db
from app.editing.store import apply_composition_edits
from app.main import app as main_app
from app.models.schemas import AssetType
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    Output,
    Project,
    SourceSnapshot,
    User,
    Wallet,
)
from app.providers.llm.base import ToolGeneration
from test.support.composition_fixtures import (
    AUDIO_DIGEST,
    AUDIO_SNAPSHOT,
    FOUR_S_TICKS,
    IMG_DIGEST,
    IMG_SNAPSHOT,
    creation_ops,
)


async def _user(factory, **kwargs) -> UUID:
    async with factory() as db:
        user = User(email=f"{uuid4()}@example.test", name="test", **kwargs)
        db.add(user)
        await db.commit()
        return user.id


async def _project(factory, user_id: UUID, title: str = "chat", **kwargs) -> UUID:
    async with factory() as db:
        project = Project(user_id=user_id, title=title, **kwargs)
        db.add(project)
        await db.commit()
        return project.id


async def _snapshots(factory, owner_id: UUID) -> None:
    async with factory() as db:
        db.add_all(
            [
                SourceSnapshot(
                    id=IMG_SNAPSHOT,
                    owner_id=owner_id,
                    kind="image",
                    storage_key="snapshots/img.png",
                    digest=IMG_DIGEST,
                    duration_ticks=None,
                ),
                SourceSnapshot(
                    id=AUDIO_SNAPSHOT,
                    owner_id=owner_id,
                    kind="audio",
                    storage_key="snapshots/bed.wav",
                    digest=AUDIO_DIGEST,
                    duration_ticks=FOUR_S_TICKS,
                ),
            ]
        )
        await db.commit()


async def _create(factory, owner_id: UUID, project_id: UUID, request_id=None, name: str = "sample"):
    async with factory() as db:
        return await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=project_id,
            ops=creation_ops(),
            request_id=request_id,
            name=name,
        )


def client_for(database, uid: UUID) -> httpx.AsyncClient:
    """Lightweight ASGI client exposing project + output routes for lock/deletion races."""
    projects = import_module("app.pipeline.routes.projects")
    sub_app = FastAPI()
    sub_app.include_router(projects.router, prefix="/projects")
    sub_app.include_router(import_module("app.pipeline.routes.outputs").router, prefix="/outputs")

    async def session():
        async with database() as db:
            yield db

    sub_app.dependency_overrides[get_db] = session
    sub_app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=uid)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=sub_app), base_url="http://test")


def bind_test_database(monkeypatch, database) -> None:
    """Point app.models.database.AsyncSessionLocal and every top-level importer at ``database``."""
    import sys

    targets = (
        "app.models.database",
        "app.chat.editor",
        "app.chat.editor_media",
        "app.chat.conversation_context",
        "app.tools.project_context",
        "app.tools.video.design",
        "app.tools.video.brand",
        "app.tools.video.music_preparation",
        "app.tools.video.sfx_synthesis",
        "app.tools.video.visual_assets",
        "app.tools.world",
        "app.pipeline.export_jobs",
        "app.pipeline.media_jobs",
    )
    for mod_name in targets:
        mod = sys.modules.get(mod_name)
        if mod is None:
            mod = import_module(mod_name)
        if hasattr(mod, "AsyncSessionLocal"):
            monkeypatch.setattr(mod, "AsyncSessionLocal", database)


@asynccontextmanager
async def full_api_client(database, user: User):
    """Full ASGI client mounted against the real FastAPI app (auto-clears overrides on exit)."""
    async def _override_db():
        async with database() as session:
            yield session

    async def _override_user():
        return user

    main_app.dependency_overrides[get_db] = _override_db
    main_app.dependency_overrides[get_current_user_required] = _override_user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main_app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        main_app.dependency_overrides.clear()


async def seed_project_with_receipt(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    async with database() as db:
        conversation = Conversation(project_id=pid, user_id=uid)
        asset = Asset(project_id=pid, user_id=uid, type=AssetType.VIDEO, file_url="synthetic/video.mp4")
        db.add_all([conversation, asset, Wallet(user_id=uid, balance=100), Output(project_id=pid, type="video")])
        await db.flush()
        db.add(
            SourceSnapshot(
                owner_id=uid,
                asset_id=asset.id,
                origin_project_id=pid,
                kind="video",
                storage_key="snapshots/synthetic.mp4",
                digest="a" * 64,
            )
        )
        receipt = Message(
            conversation_id=conversation.id,
            role="assistant",
            content="",
            seq=1,
            intent={"tool": "generate_music", "editor_media": str(uuid4())},
        )
        db.add(receipt)
        await db.commit()
        return uid, pid, receipt.id


async def snapshot_db_state(database) -> dict:
    async with database() as db:
        return {
            table: list(await db.scalars(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")))
            for table in (
                "projects",
                "assets",
                "source_snapshots",
                "outputs",
                "media_jobs",
                "export_jobs",
                "conversations",
                "messages",
                "wallets",
                "credit_transactions",
            )
        }


class ScriptedToolClient:
    """Deterministic scripted LLM client for Layer 1A Chat-Origin ASGI tests."""

    model = "test-eval-model-v1"

    def __init__(self, generations: list[ToolGeneration], *, streaming: bool = False):
        self._generations = list(generations)
        self.calls: list[dict] = []
        self.capabilities = SimpleNamespace(
            supports_native_tools=True,
            supports_streaming=streaming,
        )

    async def generate_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        assert self._generations, "Unexpected extra LLM iteration in ScriptedToolClient"
        return self._generations.pop(0)

    async def generate_stream_with_tools(self, **kwargs):
        gen = await self.generate_with_tools(**kwargs)
        on_delta = kwargs.get("on_delta")
        if on_delta is not None and gen.content:
            emitted = on_delta(gen.content)
            if isawaitable(emitted):
                await emitted
        return gen


@contextmanager
def disposable_postgres():
    """Create an empty database for the duration of a test or session."""
    db_name = f"rep_test_v2_{uuid4().hex[:12]}"
    async_server = settings.database_url.rsplit("/", 1)[0]
    sync_server = async_server.replace("postgresql+asyncpg", "postgresql+psycopg2")

    admin = create_engine(f"{sync_server}/postgres", isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        conn.execute(text(f'ALTER DATABASE "{db_name}" SET synchronous_commit = off'))

    try:
        yield f"{async_server}/{db_name}", f"{sync_server}/{db_name}"
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
        admin.dispose()
