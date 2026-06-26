"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.database import init_db
from app.routers import (
    assets,
    brand_templates,
    clips,
    derivatives,
    files,
    projects,
    speaker_assets,
    speakers,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    settings.ensure_dirs()
    await init_db()
    yield


app = FastAPI(
    title="Repurposer API",
    description="AI-powered speech content repurposing platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(speakers, prefix="/api/v1/speakers", tags=["speakers"])
app.include_router(projects, prefix="/api/v1/projects", tags=["projects"])
app.include_router(assets, prefix="/api/v1/projects", tags=["assets"])
app.include_router(speaker_assets, prefix="/api/v1/speakers", tags=["speaker-assets"])
app.include_router(clips, prefix="/api/v1/clips", tags=["clips"])
app.include_router(derivatives, prefix="/api/v1/derivatives", tags=["derivatives"])
app.include_router(files, prefix="/api/v1", tags=["files"])
app.include_router(
    brand_templates, prefix="/api/v1/brand-templates", tags=["brand-templates"]
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
