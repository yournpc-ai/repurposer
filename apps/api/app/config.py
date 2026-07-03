"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Minimax
    minimax_api_key: str = ""
    minimax_model: str = "minimax-m3"
    minimax_base_url: str = "https://api.minimax.io/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/repurposer"

    # Storage
    asset_dir: Path = Path("./assets")
    # Deprecated: upload_dir/output_dir are kept for compatibility during the
    # migration to asset_dir; new code should use asset_dir directly.
    upload_dir: Path = Path("./data/uploads")
    output_dir: Path = Path("./data/outputs")
    music_dir: Path = Path("./data/music")  # built-in mood music library

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

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

    def ensure_dirs(self) -> None:
        """Ensure storage directories exist."""
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.music_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
