"""FastAPI application entry point."""

import json
import logging
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.models.database import AsyncSessionLocal, init_db
from app.chat.routes import chat_router
from app.distribution.routes import router as distribution_router
from app.memory.brand import seed_default_brand_template
from app.memory.routes import brand_templates_router, personas_router
from app.pipeline.music import seed_default_music
from app.pipeline.registry import assert_runners_registered
from app.pipeline.routes import (
    assets,
    music,
    outputs,
    persona_assets,
    projects,
    recipes,
    runs,
)
from app.platform.routes import auth_router, files_router, notifications_router
from app.operations.routes import router as operations_router

logger = logging.getLogger(__name__)
request_logger = structlog.get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    settings.ensure_dirs()
    assert_runners_registered()
    await init_db()
    await seed_default_brand_template()
    async with AsyncSessionLocal() as db:
        await seed_default_music(db)
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


# Keys whose values must never land in logs (credentials, one-time codes).
_SENSITIVE_KEYS = {"token", "password", "code", "secret", "api_key", "authorization"}
_MAX_BODY_LOG = 2048


def _redact(obj):
    if isinstance(obj, dict):
        return {
            k: ("***" if str(k).lower() in _SENSITIVE_KEYS else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(item) for item in obj[:20]]
    return obj


def _body_for_log(raw: bytes) -> str | None:
    """Render a request/response body for the log: JSON with sensitive values
    redacted, truncated to a bounded size; non-JSON is summarized by size."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return f"<{len(raw)} bytes non-json>"
    text = json.dumps(_redact(parsed), ensure_ascii=False, default=str)
    return text[:_MAX_BODY_LOG] + ("…" if len(text) > _MAX_BODY_LOG else "")


@app.middleware("http")
async def log_requests(request, call_next):
    """Production request log: input, output, status, duration, client.

    Records the path as received (post-proxy), query string, JSON request
    body, and JSON response body (with credentials redacted) — the ground
    truth for diagnosing reverse-proxy prefix issues (e.g. /api stripping)
    and "which input caused this 4xx" questions that status-only logs
    can't answer. Multipart/binary payloads and file streaming are never
    buffered; they are logged by size only.
    """
    if request.url.path == "/health":
        return await call_next(request)
    start = time.monotonic()

    # Only buffer JSON request bodies. No receive-channel patching needed:
    # under BaseHTTPMiddleware the request is a _CachedRequest — body() caches
    # the body and replays it to downstream handlers automatically. Patching
    # _receive actively breaks streaming responses: after the body is consumed,
    # StreamingResponse's disconnect probe calls receive() expecting
    # http.disconnect, and a replayed http.request trips starlette's
    # "Unexpected message received" guard (chat SSE, 2026-08-04).
    request_body: bytes | None = None
    request_content_type = request.headers.get("content-type", "")
    if "application/json" in request_content_type:
        request_body = await request.body()

    response = await call_next(request)

    # Only buffer JSON responses; streaming/file downloads pass through
    # untouched (buffering them would defeat Range and balloon memory).
    response_body: bytes | None = None
    if "application/json" in response.headers.get("content-type", ""):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        response_body = b"".join(chunks)
        response = Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            background=response.background,
        )

    duration_ms = round((time.monotonic() - start) * 1000)
    forwarded_for = request.headers.get("x-forwarded-for", "")
    request_logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        query=str(request.url.query) or None,
        status=response.status_code,
        duration_ms=duration_ms,
        client_ip=(
            forwarded_for.split(",")[0].strip()
            or (request.client.host if request.client else None)
        ),
        user_agent=request.headers.get("user-agent", "")[:80],
        request_body=_body_for_log(request_body) if request_body else None,
        response_body=_body_for_log(response_body) if response_body else None,
    )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Unified 4xx/5xx handling: log the reason, return it in the response.

    The request middleware logs the response body too, but it only sees the
    final response — this handler records the reason at raise time (and, for
    the 500 handler below, the traceback, which never reaches a response
    body). Response shape matches FastAPI's default ({"detail": ...}), so
    clients are unaffected.
    """
    if exc.status_code >= 400:
        request_logger.warning(
            "http_error",
            method=request.method,
            path=request.url.path,
            status=exc.status_code,
            detail=exc.detail,
        )
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log which fields failed validation instead of a bare 422."""
    errors = exc.errors()
    request_logger.warning(
        "http_validation_error",
        method=request.method,
        path=request.url.path,
        status=422,
        detail=errors[:5],  # bound log size on pathological payloads
    )
    return JSONResponse({"detail": errors}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort 500: log the traceback server-side, return a safe JSON body."""
    request_logger.exception(
        "http_unhandled_error",
        method=request.method,
        path=request.url.path,
        status=500,
    )
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(personas_router, prefix="/api/v1/personas", tags=["personas"])
app.include_router(projects, prefix="/api/v1/projects", tags=["projects"])
app.include_router(runs, prefix="/api/v1/runs", tags=["runs"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(assets, prefix="/api/v1/projects", tags=["assets"])
app.include_router(persona_assets, prefix="/api/v1/personas", tags=["persona-assets"])
app.include_router(outputs, prefix="/api/v1/outputs", tags=["outputs"])
app.include_router(operations_router, prefix="/api/v1/outputs", tags=["operations"])
app.include_router(files_router, prefix="/api/v1", tags=["files"])
app.include_router(music, prefix="/api/v1/music", tags=["music"])
app.include_router(recipes, prefix="/api/v1/recipes", tags=["recipes"])
app.include_router(
    brand_templates_router, prefix="/api/v1/brand-templates", tags=["brand-templates"]
)
# Distribution: /api/v1/channels/* + /api/v1/publications/* (URL names the
# resource, not the module — DISTRIBUTION.md §1.1)
app.include_router(distribution_router, prefix="/api/v1", tags=["distribution"])
app.include_router(notifications_router, prefix="/api/v1", tags=["notifications"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
