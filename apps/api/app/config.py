"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Minimax
    minimax_api_key: str = ""
    minimax_model: str = "minimax-m3"
    minimax_base_url: str = "https://api.minimax.io/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/repurposer"

    # S3-compatible object storage (Volcengine TOS, AWS S3, MinIO, etc.)
    s3_endpoint_url: str
    s3_bucket_name: str
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_region: str = "ap-southeast-1"
    s3_public_url: str  # public read base URL, e.g. https://bucket.tos-region.volces.com
    s3_force_path_style: bool = False  # MUST be False for Volcengine TOS
    s3_presign_upload_ttl: int = 900  # presigned PUT URL TTL in seconds

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8000,http://127.0.0.1:8000,"
        "https://repurposer.yournpc.ai",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Demo seeding
    skip_demo_seed: bool = False
    demo_seed_async: bool = False

    # Background worker
    worker_poll_interval: float = 2.0

    # ASR (faster-whisper, self-hosted — EU/GDPR; CTranslate2, no torch)
    asr_model: str = "base"  # tiny/base/small/medium/large-v3
    asr_device: str = "cpu"  # cpu | cuda
    asr_compute_type: str = "int8"  # int8 (cpu) | float16 (gpu)

    # Video render service (Remotion, apps/render — black box: spec -> MP4+SRT)
    render_url: str = "http://localhost:3001/render"
    # Public base of this API, used to absolutize source URLs the render service
    # fetches (clip-spec stores relative stream URLs via the storage seam).
    api_public_url: str = "http://localhost:8000"

    # Auth / email
    resend_api_key: str = ""
    from_email: str = "Repurposer <no-reply@repurposer.local>"
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_expire_days: int = 30

    # Distribution — channel OAuth (presence-gating: empty = channel hidden in
    # UI, docs/DISTRIBUTION.md §4.1; no feature flags)
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    # Fernet key for channel token encryption (ADR-031). Empty = plaintext
    # storage with a warning (local dev only); prod must set this.
    channel_credentials_key: str = ""

    def ensure_dirs(self) -> None:
        """No local media directories are used; all persistence is object storage."""


settings = Settings()
