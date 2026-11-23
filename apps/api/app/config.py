"""Application configuration."""

import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


MINIMAX_FLASH_MODEL = "MiniMax-M3.1-Flash"


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Text/code LLM provider. Media generation stays with its own providers.
    llm_provider: Literal["minimax", "deepseek", "gemini"] = "minimax"

    # Minimax
    minimax_api_key: str = ""
    minimax_model: str = MINIMAX_FLASH_MODEL
    minimax_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] = "xhigh"
    minimax_base_url: str = "https://api.minimax.io/v1"
    # Startup prefix-cache warmup (批3): one throwaway call per chat agent at
    # API boot seeds the passive prefix cache on one backend pod (forensics
    # 2026-09-27). Fire-and-forget, never blocks startup.
    minimax_warmup_enabled: bool = True
    # Local, opt-in full request/response capture for every text/code provider.
    # Empty = off. The old MINIMAX_JOURNEY_TRACE environment name remains an alias.
    llm_trace_path: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_TRACE_PATH", "MINIMAX_JOURNEY_TRACE"),
    )

    # Operator-managed Skill releases. Each path points to the installed
    # package directory. Keep release directories immutable after activation.
    managed_skill_root: Path | None = None
    managed_skill_versions: dict[str, str] = Field(default_factory=dict)

    # DeepSeek text/code generation. Tool loops are non-thinking until the
    # harness can replay DeepSeek's required historical reasoning_content.
    deepseek_api_key: str = ""

    # Opt-in Gemini native audio-video multimodal adapter for controlled
    # side-by-side comparison. Empty key never affects the default provider.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    deepseek_model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_reasoning_effort: Literal["low", "high", "max"] = "high"
    # Explicit cap: DeepSeek otherwise defaults non-thinking responses to 8K,
    # which truncates large Composition tool arguments before JSON parsing.
    deepseek_max_output_tokens: int = Field(default=32768, ge=1, le=393216)
    # Comma-separated YYYY-MM-DD public holidays treated as off-peak.
    deepseek_offpeak_dates: str = ""
    # Accounting conversion for DeepSeek's CNY price list; override with the
    # deployment's contract/accounting rate when it differs.
    deepseek_cny_per_usd: float = Field(default=7.2, gt=0)

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/repurposer"

    # S3-compatible object storage (Volcengine TOS, AWS S3, MinIO, etc.)
    s3_endpoint_url: str
    s3_bucket_name: str
    s3_access_key_id: str
    s3_secret_access_key: str
    # Optional HTTP(S) proxy for DOWNLOADS only (dev machines behind a
    # throttled direct route: TOS direct ~119KB/s vs proxy ~13MB/s). Empty =
    # direct everywhere (prod default — never set this on the Docker deploy
    # unless the host needs it). Uploads NEVER ride this: the local proxy
    # swallows large-PUT responses (the upload-stall trap), so writes stay
    # on the direct client by construction.
    storage_get_proxy: str = ""
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

    # Background worker
    worker_poll_interval: float = 2.0
    # Direction interrupt expiry (期 4): a parked interrupt is auto-answered
    # with its default option after this long — the review tier degrades to
    # best-judgment completion, never a bail and never a permanent park.
    interrupt_expiry_seconds: int = 1800

    # Poison-pill caps (R1 B4a): claims of a queue row beyond the cap flip it
    # to its FAILED terminal instead of re-entering the crash loop. Boundary:
    # attempt == cap is still claimable, attempt > cap is terminal (total
    # executions = cap + 1). Same magnitude as the node-level budgets
    # (NodeBase.retries 0–2). The tick cadence is the backoff — no retry
    # schedule is invented here.
    asset_max_attempts: int = 3
    render_max_attempts: int = 3
    # Render execution knobs (MG D4 — engineering parameters, deployment-shaped,
    # so env Settings, NOT the configs table; boundary rule = platform/configs.py
    # header §3). render_concurrency caps simultaneous renders per worker process
    # (the contended resource is headless Chrome in the render service; 2 keeps
    # one Chrome crash from stalling the queue while bounding memory).
    # render_timeout_seconds fences one render-service POST: the film baseline is
    # ≈46s for a 26s film (local spike, ~1.75× realtime), but the SAME fence
    # covers video production, where longer sources legitimately render for
    # minutes. 1800s includes the shared 12-minute upload retry budget.
    render_concurrency: int = 2
    render_timeout_seconds: int = 1800

    # Upstream component bake stays fail-closed until the deployment provides
    # real process/filesystem/egress/resource isolation. Source scanning is
    # diagnostic only and is never the security boundary. This is a deployment
    # guard shared by API and render, not a user-facing capability preference.
    component_bake_enabled: bool = False

    # Freesound official API for CC0 SFX search/import. Empty = honest unavailable.
    freesound_api_key: str = ""

    # ASR (faster-whisper, self-hosted — EU/GDPR; CTranslate2, no torch)
    asr_model: str = "base"  # tiny/base/small/medium/large-v3
    asr_device: str = "cpu"  # cpu | cuda
    asr_compute_type: str = "int8"  # int8 (cpu) | float16 (gpu)

    # Web page capture (tools/research/capture.py — URL → web_page asset).
    # chrome_path empty = platform candidates + PATH lookup (resolve_chrome_path
    # is the ONE seat — spike/render/worker never re-derive it). no_sandbox for
    # container workers without user namespaces; keep False on real hosts.
    chrome_path: str = ""
    chrome_no_sandbox: bool = False
    # Capture caps (SSRF browser-level policy): the whole browser session's
    # wall clock, and the policy proxy's per-capture request/byte budgets.
    # ADR-121 B1 re-estimate: the playwright session scroll-preloads (lazy
    # loads fire) and shoots fold + ≤5 sections — the one-shot CLI's budgets
    # (25s / 200 conns) choked that (scroll = more connections, more wall).
    web_capture_timeout_seconds: float = 90.0
    web_capture_max_requests: int = 500
    web_capture_max_bytes: int = 60 * 1024 * 1024
    # HTML fetch half's body cap (the grounding manifest's source).
    web_capture_html_max_bytes: int = 2 * 1024 * 1024

    # Video render service (Remotion, apps/render — black box: spec -> MP4+SRT)
    render_url: str = "http://localhost:3001/render"
    # Public base of this API, used to absolutize source URLs the render service
    # fetches (video-spec stores relative stream URLs via the storage seam).
    api_public_url: str = "http://localhost:8000"
    # Public base of the web app — OAuth callbacks redirect the browser back here.
    web_public_url: str = "http://localhost:3000"

    # Payments — hosted Stripe Checkout; amounts and credits stay server-side.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Comma-separated operations recipients. Only the worker needs this value;
    # webhook requests persist the alert outbox without calling Resend inline.
    payment_alert_recipients: str = ""

    @property
    def payment_alert_recipient_list(self) -> list[str]:
        return [
            recipient.strip()
            for recipient in self.payment_alert_recipients.split(",")
            if recipient.strip()
        ]

    # Auth / email
    resend_api_key: str = ""
    from_email: str = "Rookie Cut <no-reply@repurposer.local>"
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_expire_days: int = 1

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
