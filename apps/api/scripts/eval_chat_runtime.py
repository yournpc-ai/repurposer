"""Disposable API and worker sharing the same migrated database and local media URLs."""

import asyncio
import os
import socket
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts.run_pytest import _find_env_file

API_ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def service(args, env, log_path, **kwargs):
    with log_path.open("w") as log:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            *args,
            cwd=API_ROOT,
            env=env,
            stdout=log,
            stderr=asyncio.subprocess.STDOUT,
            **kwargs,
        )
        try:
            yield proc
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=10)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()


@asynccontextmanager
async def live_project(name, out_dir, keep_db):
    # Load the worktree's configuration before importing application settings.
    if env_file := _find_env_file():
        for key, value in dotenv_values(env_file).items():
            if value is not None:
                os.environ.setdefault(key, value)

    from app.config import settings
    from app.models.tables import Project, User, Wallet
    from app.platform.auth import create_access_token

    db_name = f"rep_eval_{uuid4().hex[:10]}"
    server = settings.database_url.rsplit("/", 1)[0]
    url = f"{server}/{db_name}"
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    storage_dir = out_dir.resolve() / "local_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncExitStack() as stack:
        stack.push_async_callback(admin.dispose)
        connection = await stack.enter_async_context(admin.connect())
        await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
        if not keep_db:
            stack.push_async_callback(
                connection.execute, text(f'DROP DATABASE "{db_name}" WITH (FORCE)')
            )

        sock = stack.enter_context(socket.socket())
        sock.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
        env = dict(
            os.environ,
            DATABASE_URL=url,
            S3_ENDPOINT_URL=f"local://{storage_dir}",
            S3_PUBLIC_URL=f"{origin}/_local_storage",
            API_PUBLIC_URL=origin,
            MINIMAX_WARMUP_ENABLED="false",
        )
        migration = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "head",
            cwd=API_ROOT,
            env=env,
        )
        if await migration.wait():
            raise RuntimeError("Could not migrate disposable eval database")

        engine = create_async_engine(url)
        stack.push_async_callback(engine.dispose)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as db:
            user = User(
                email=f"{db_name}@rookiecut.local",
                name="Eval Harness",
                settings={"confirm_execution": "auto", "confirm_credits": "auto"},
            )
            db.add(user)
            await db.flush()
            db.add(Wallet(user_id=user.id, balance=5000))
            project = Project(user_id=user.id, title=f"Eval: {name}", language="zh")
            db.add(project)

        api = await stack.enter_async_context(
            service(
                ["uvicorn", "app.main:app", "--fd", str(sock.fileno())],
                env,
                out_dir / "api.log",
                pass_fds=(sock.fileno(),),
            )
        )
        client = await stack.enter_async_context(
            httpx.AsyncClient(
                base_url=origin,
                trust_env=False,
                timeout=settings.render_timeout_seconds + 240,
                headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
            )
        )
        async with asyncio.timeout(60):
            while api.returncode is None:
                try:
                    if (await client.get("/health", timeout=1)).is_success:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.2)
            else:
                raise RuntimeError(f"Eval API failed to start; see {out_dir / 'api.log'}")
        await stack.enter_async_context(service(["app.worker"], env, out_dir / "worker.log"))
        yield client, sessions, user.id, project.id, storage_dir
