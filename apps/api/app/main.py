"""FastAPI application entry point."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.database import AsyncSessionLocal, init_db
from app.routers import (
    assets,
    auth,
    brand_templates,
    chat,
    clips,
    derivatives,
    files,
    intent,
    library,
    music,
    projects,
    speaker_assets,
    speakers,
)
from app.services.brand import seed_default_brand_template
from app.services.demo_seed import seed_demo_project
from app.services.music import seed_default_music

logger = logging.getLogger(__name__)
request_logger = structlog.get_logger("http")


def _log_demo_seed_result(task: asyncio.Task) -> None:
    """Log any exception from the async demo seed task."""
    try:
        task.result()
    except Exception as e:
        logger.exception("demo_seed_async_failed", exc_info=e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    settings.ensure_dirs()
    await init_db()
    await seed_default_brand_template()
    async with AsyncSessionLocal() as db:
        await seed_default_music(db)
    if not settings.skip_demo_seed:
        if settings.demo_seed_async:
            task = asyncio.create_task(seed_demo_project())
            task.add_done_callback(_log_demo_seed_result)
        else:
            await seed_demo_project()
    yield


app = FastAPI(
    title="Repurposer API",
    description="AI-powered speech content repurposing platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request, call_next):
    """Log every request with the path as received (post-proxy), client IP,
    status, and duration — the ground truth for diagnosing reverse-proxy
    prefix issues (e.g. /api stripping) that browser-side logs can't show."""
    start = time.monotonic()
    response = await call_next(request)
    if request.url.path == "/health":
        return response
    duration_ms = round((time.monotonic() - start) * 1000)
    forwarded_for = request.headers.get("x-forwarded-for", "")
    request_logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        client_ip=(
            forwarded_for.split(",")[0].strip()
            or (request.client.host if request.client else None)
        ),
        user_agent=request.headers.get("user-agent", "")[:80],
    )
    return response

app.include_router(auth, prefix="/api/v1/auth", tags=["auth"])
app.include_router(speakers, prefix="/api/v1/speakers", tags=["speakers"])
app.include_router(projects, prefix="/api/v1/projects", tags=["projects"])
app.include_router(chat, prefix="/api/v1/chat", tags=["chat"])
app.include_router(assets, prefix="/api/v1/projects", tags=["assets"])
app.include_router(speaker_assets, prefix="/api/v1/speakers", tags=["speaker-assets"])
app.include_router(clips, prefix="/api/v1/clips", tags=["clips"])
app.include_router(derivatives, prefix="/api/v1/derivatives", tags=["derivatives"])
app.include_router(library, prefix="/api/v1/library", tags=["library"])
app.include_router(files, prefix="/api/v1", tags=["files"])
app.include_router(music, prefix="/api/v1/music", tags=["music"])
app.include_router(intent, prefix="/api/v1", tags=["intent"])
app.include_router(
    brand_templates, prefix="/api/v1/brand-templates", tags=["brand-templates"]
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
