"""T2a acceptance stack launcher (local isolated DB, MiniMax request fence).

Starts either the API or the worker against the isolated ``repurposer_t2a``
database with the film edit gate on and warmup off. The fence counts MiniMax
HTTP requests and trips BEFORE firing past the configured cap.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/repurposer_t2a",
)
os.environ.setdefault("FILM_EDITS_ENABLED", "true")
os.environ.setdefault("MINIMAX_WARMUP_ENABLED", "false")
os.environ.setdefault("API_PUBLIC_URL", "http://127.0.0.1:8002")


class ProviderFenceTripped(RuntimeError):
    pass


def install_fence(cap: int, wall_seconds: float) -> None:
    import httpx

    from app.config import settings

    host_marker = settings.minimax_base_url.split("//", 1)[-1].split("/")[0]
    state = {"count": 0, "t0": time.monotonic()}
    real_post = httpx.AsyncClient.post
    real_stream = httpx.AsyncClient.stream

    def fence(url: str) -> None:
        if host_marker not in str(url):
            return
        if state["count"] >= cap:
            raise ProviderFenceTripped(f"MiniMax request budget exhausted ({cap})")
        if time.monotonic() - state["t0"] > wall_seconds:
            raise ProviderFenceTripped(f"wall-clock deadline exceeded ({wall_seconds}s)")
        state["count"] += 1
        print(f"[t2a-fence] MiniMax request #{state['count']}/{cap}", flush=True)

    async def fenced_post(self, url, **kwargs):
        fence(str(url))
        return await real_post(self, url, **kwargs)

    def fenced_stream(self, method, url, **kwargs):
        fence(str(url))
        return real_stream(self, method, url, **kwargs)

    httpx.AsyncClient.post = fenced_post  # type: ignore[method-assign]
    httpx.AsyncClient.stream = fenced_stream  # type: ignore[method-assign]
    print(
        f"[t2a-fence] armed host={host_marker} cap={cap} wall={wall_seconds}s",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("api", "worker"))
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--cap", type=int, default=180)
    parser.add_argument("--wall", type=float, default=3600.0)
    args = parser.parse_args()

    install_fence(args.cap, args.wall)
    if args.mode == "api":
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=args.port,
            log_level="info",
        )
        return

    from app.worker import main as worker_main

    worker_main()


if __name__ == "__main__":
    main()
