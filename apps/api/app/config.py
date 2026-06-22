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
    upload_dir: Path = Path("./data/uploads")
    output_dir: Path = Path("./data/outputs")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    def ensure_dirs(self) -> None:
        """Ensure storage directories exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
