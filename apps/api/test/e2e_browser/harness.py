"""Offline Studio stack. Only the LLM and email delivery are replaced."""
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import httpx
from playwright.async_api import async_playwright, expect
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import uvicorn

from app.chat.intent import intent_router
from app.config import settings
from app.tools.video.preparation import ensure_font_resources
from app.main import app
from app.models import database as database_module
from app.models.tables import Conversation, Message
from app.platform.auth import create_verification_code
from test.support.db_helpers import ScriptedToolClient, _project, bind_test_database, disposable_postgres

ROOT = Path(__file__).resolve().parents[4]
HOST = "127.0.0.1"


def chrome_path(chromium):
    candidates = [os.environ.get("E2E_CHROME_PATH"), chromium.executable_path,
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  *sorted((ROOT / "apps/render/node_modules/.remotion/chrome-headless-shell")
                          .glob("**/chrome-headless-shell"))]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    pytest.fail(f"No local executable Chromium found. Checked {candidates}. Set E2E_CHROME_PATH.")


@pytest.fixture(scope="session")
def studio_server(tmp_path_factory):
    # Vite's router plugin generates sources. Build a private copy of Studio.
    source = ROOT / "apps/web"
    web = tmp_path_factory.mktemp("studio")
    for name in ("src", "public"):
        shutil.copytree(source / name, web / name)
    for name in (".gitignore", "vite.config.ts", "package.json", "tsconfig.json", "tsr.config.json"):
        shutil.copyfile(source / name, web / name)
    (web / "node_modules").symlink_to(source / "node_modules", target_is_directory=True)
    with socket.socket() as api_socket, socket.socket() as port:
        api_socket.bind((HOST, 0))
        port.bind((HOST, 0))
        web_port = port.getsockname()[1]
        port.close()
        origin = f"http://{HOST}:{web_port}"
        api = f"http://{HOST}:{api_socket.getsockname()[1]}"
        script = """
            import { createBuilder, preview } from 'vite';
            await (await createBuilder({})).buildApp();
            await preview({ preview: {
              host: '127.0.0.1', port: Number(process.env.WEB_PORT), strictPort: true,
              proxy: { '/api': process.env.API_TARGET, '/_local_storage': process.env.API_TARGET }
            } });
        """
        with (web / "vite.log").open("w") as log:
            proc = subprocess.Popen(["node", "--input-type=module", "-e", script], cwd=web,
                                    env={**os.environ, "WEB_PORT": str(web_port), "API_TARGET": api,
                                         "VITE_API_URL": origin}, stdout=log, stderr=subprocess.STDOUT)
            try:
                with httpx.Client(trust_env=False, timeout=2) as client:
                    deadline = time.monotonic() + 120
                    while time.monotonic() < deadline and proc.poll() is None:
                        try:
                            if client.get(origin).is_success:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(.2)
                    else:
                        pytest.fail((web / "vite.log").read_text()[-3500:])
                yield origin, api_socket
            finally:
                proc.terminate()
                proc.wait(timeout=15)


@asynccontextmanager
async def backend(monkeypatch, tmp_path, sock):
    with disposable_postgres() as (url, _):
        monkeypatch.setattr(settings, "database_url", url)
        monkeypatch.setattr(settings, "s3_endpoint_url", f"local://{tmp_path}")
        await ensure_font_resources()
        monkeypatch.setattr(settings, "minimax_warmup_enabled", False)
        monkeypatch.setattr(settings, "jwt_secret_key", uuid4().hex * 2)
        command.upgrade(Config("alembic.ini"), "head")
        engine = create_async_engine(url)
        database = async_sessionmaker(engine, expire_on_commit=False)
        original = database_module.AsyncSessionLocal
        bind_test_database(monkeypatch, database)
        for module in list(sys.modules.values()):
            if (getattr(module, "__name__", "").startswith("app.")
                    and vars(module).get("AsyncSessionLocal") is original):
                monkeypatch.setattr(module, "AsyncSessionLocal", database)
        monkeypatch.setattr(database_module, "engine", engine)
        llm = ScriptedToolClient([], streaming=True)
        llm.provider = "scripted"
        monkeypatch.setattr(intent_router, "client", llm)
        monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: llm)
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        task = asyncio.create_task(server.serve(sockets=[sock.dup()]))
        try:
            async with asyncio.timeout(30):
                while not server.started:
                    if task.done():
                        await task
                        pytest.fail("FastAPI startup failed")
                    await asyncio.sleep(.02)
            yield database, llm
        finally:
            server.should_exit = True
            await task
            await engine.dispose()


@dataclass
class Studio:
    page: object
    database: object
    project: UUID
    llm: ScriptedToolClient
    folder: Path
    report: dict = field(default_factory=lambda: {
        "dom": [], "pg": {}, "console": Counter(), "responses": Counter(), "errors": [],
    })

    def script(self, *generations):
        assert not self.llm._generations
        self.llm._generations.extend(generations)

    async def send(self, message):
        composer = self.page.get_by_role("textbox")
        await composer.fill(message)
        async with self.page.expect_response(lambda r: r.url.endswith("/api/v1/chat")
                                            and r.request.method == "POST") as pending:
            await composer.press("Enter")
        response = await pending.value
        assert response.status == 200 and "text/event-stream" in response.headers["content-type"]
        return response

    async def messages(self):
        async with self.database() as db:
            rows = list(await db.scalars(select(Message).join(Conversation)
                                         .where(Conversation.project_id == self.project)
                                         .order_by(Message.seq)))
        self.report["pg"]["messages"] = len(rows)
        return rows

    async def capture(self, name, *locators):
        locators = tuple(self.page.locator("body") if loc is self.page else loc for loc in locators)
        for locator in locators:
            await expect(locator).to_be_visible(timeout=15000)
        await self.page.screenshot(path=self.folder / f"{name}.png", full_page=True, animations="disabled")
        self.report["dom"].append({"step": name, "visible": [
            (await loc.get_attribute("aria-label")) or (await loc.inner_text())[:240] or str(loc)
            for loc in locators
        ]})


@pytest.fixture
async def studio(request, studio_server, tmp_path, monkeypatch):
    origin, sock = studio_server
    monkeypatch.setattr(settings, "s3_public_url", origin + "/_local_storage")
    async with backend(monkeypatch, tmp_path, sock) as (database, llm), async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=chrome_path(pw.chromium))
        try:
            email = f"{uuid4()}@example.test"
            async with database() as db:
                code = (await create_verification_code(db, email)).code
            async with httpx.AsyncClient(base_url=origin, trust_env=False) as client:
                response = await client.post("/api/v1/auth/verify-code", json={"email": email, "code": code})
                response.raise_for_status()
                auth = response.json()
            project = await _project(database, UUID(auth["user"]["id"]), "Launch studio", language="en")
            async with database() as db:
                db.add(Conversation(project_id=project, user_id=UUID(auth["user"]["id"]), ui_language="en"))
                await db.commit()
            context = await browser.new_context(locale="en-US", reduced_motion="reduce", viewport={"width": 1440, "height": 950},
                storage_state={"cookies": [], "origins": [{"origin": origin, "localStorage": [
                    {"name": "repurposer-token", "value": auth["token"]},
                    {"name": "repurposer-user", "value": json.dumps(auth["user"])},
                ]}]})
            await context.add_cookies([{"name": "repurposer-lang", "value": "en", "url": origin}])
            await context.tracing.start(screenshots=True, snapshots=True)
            page = await context.new_page()
            folder = ROOT / "scratch/e2e-audit" / request.node.name
            folder.mkdir(parents=True, exist_ok=True)
            for old in [*folder.glob("*.png"), folder / "trace.zip", folder / "failure.txt", folder / "report.json"]:
                old.unlink(missing_ok=True)
            case = Studio(page, database, project, llm, folder)
            report = case.report

            def on_response(response):
                report["responses"][response.status] += 1
                if response.status >= 400:
                    report.setdefault("http_errors", []).append([response.status, urlsplit(response.url).path])
                if response.status >= 500:
                    report["errors"].append(f"{response.status} {response.url}")

            page.on("response", on_response)
            page.on("pageerror", lambda error: report["errors"].append(str(error)))
            page.on("console", lambda msg: report["console"].update([msg.type]))
            try:
                await page.goto(f"{origin}/projects/{project}")
                await expect(page.get_by_role("textbox")).to_be_visible(timeout=30000)
                yield case
                assert not report["errors"], report["errors"]
            finally:
                failed = (not getattr(request.node, "call_passed", False) or bool(report["errors"]))
                report["outcome"] = "failed" if failed else "passed"
                if failed:
                    await page.screenshot(path=folder / "failure.png", full_page=True, animations="disabled")
                    (folder / "failure.txt").write_text(await page.locator("body").aria_snapshot())
                await context.tracing.stop(path=folder / "trace.zip" if failed else None)
                (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
                await context.close()
        finally:
            await browser.close()
