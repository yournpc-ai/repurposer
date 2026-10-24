"""Gate-on API launcher for the R3 read smoke (local test instance ONLY).

Launches a SECOND api instance on 127.0.0.1:8001 with the film-edit gate on,
leaving the user's running :8000 API and worker untouched:

  - ``FILM_EDITS_ENABLED=true`` is injected into THIS process's environment
    (pydantic-settings: process env beats the .env file — the repo's .env
    and the default gate stay byte-untouched);
  - ``MINIMAX_WARMUP_ENABLED=false`` skips the boot warmup calls (the paid
    surface stays exactly the smoke's turns);
  - an enforced REQUEST FENCE rides the process: httpx.AsyncClient.post /
    .stream are wrapped class-level (the shared MiniMax pool rebinds per
    event loop, so the fence sits on the class) counting only calls to the
    configured MiniMax host. Past the caps the wrapper raises
    ProviderFenceTripped BEFORE the request fires — a plain RuntimeError,
    neither httpx.TransportError nor LLMError, so no retry layer swallows
    it (tenacity re-enters and re-trips instantly; zero requests past cap);
  - a RUN-CREATION BLOCKER rides the process: the sole WorkflowRun
    birthplace (``orchestrator.create_run``) is replaced BEFORE the app
    import by an unconditional refusal (layer 1 below).

The PRODUCTION-COMMIT boundary here is TWO independent layers:

  1. THE TEST-INSTANCE BLOCKER (this process only, installed below): the
     sole WorkflowRun birthplace ``orchestrator.create_run`` is replaced by
     a refusal that fires BEFORE any DB write or enqueue. It consults NO
     product state — not the review hold, not the wallet, not the
     confirmation mode, not the model's output — so even if every product
     gate were open, no run can be born through this instance. Reads,
     proposals and the smoke's isolated patch never call create_run, so
     they are untouched. Production default code and the user's :8000
     API/worker stay byte-untouched (the patch lives in THIS process).
  2. THE PRODUCT LAW UNDER TEST: each fixture project's pending film state
     carries a STANDING review_hold — ``evaluate_start_gate`` answers 422
     start.review_hold BEFORE create_run (pipeline/lifecycle.py), and
     create_run is flush-only. The smoke's L7 assertions verify this law
     directly (the hold is never released, reads never mutate state) — the
     blocker above never MASKS those assertions: they fail loudly on their
     own evidence.

The request fence is the runaway-LLM-calls guard; zero wallet + ask/ask +
the journey never approving are auxiliary layers.

Usage (from apps/api):
  uv run python scratch/run_api_gateon.py            # serves until Ctrl+C
  uv run python scratch/run_api_gateon.py --selftest # fence+blocker proof, free
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["FILM_EDITS_ENABLED"] = "true"
os.environ["MINIMAX_WARMUP_ENABLED"] = "false"

# Fence caps (enforced): the smoke journey is 6 legs; a leg's chat loop is
# bounded by max_iterations=12 (intent.py) — worst 72 logical client calls,
# each ≤3 HTTP attempts → the HTTP cap 216. Both caps are PRE-SEND checks:
# they refuse a request before it fires and never cancel one already in
# flight — a stuck in-flight call is bounded by the pool's own 120s timeout
# and the harness's 300s per-turn client timeout, not by this fence.
# Expected actuals: ~15-25 logical calls.
MAX_MINIMAX_HTTP_REQUESTS = 216
MAX_WALL_SECONDS = 3600.0


class ProviderFenceTripped(RuntimeError):
    pass


class TestRunCreationBlocked(RuntimeError):
    """The test-instance blocker's refusal at the ONLY WorkflowRun
    birthplace — a plain RuntimeError, loud in the turn's failure log,
    never a disguised business rejection."""


def _install_run_blocker():
    """Replace ``orchestrator.create_run`` with a refusal that fires BEFORE
    any DB write or enqueue. Installed BEFORE the app import (uvicorn's
    ``app.main:app`` import below), so every binding style sees it:

    - module-level ``from app.pipeline.orchestrator import create_run``
      (pipeline/routes/projects.py) imports AFTER this patch → binds the
      blocked function;
    - deferred function-level imports (chat/service.py's two seats) resolve
      the module attribute at call time → blocked.

    The refusal consults NO product state (hold / wallet / confirmation /
    model output): production through THIS instance is impossible by
    construction. Returns the blocked function for the selftest's identity
    assertions."""
    from app.pipeline import orchestrator

    async def blocked_create_run(db, project, task):
        raise TestRunCreationBlocked(
            "gate-on test instance (127.0.0.1:8001): run creation is disabled "
            "here — the R3 smoke exercises reads and the isolated patch only"
        )

    orchestrator.create_run = blocked_create_run  # type: ignore[assignment]
    return blocked_create_run


async def _selftest() -> int:
    """FREE proof of the fence + the run blocker (no server, no provider):

    1. FENCE: the class-level wrapper counts MiniMax-scoped calls and trips
       at the cap BEFORE firing (MockTransport — zero network);
    2. BLOCKER: the blocked create_run refuses with EXPLODE-ON-TOUCH
       sentinels as db/project/task — the refusal fires before ANY input is
       read (before creation and enqueue, by construction), with zero
       product state in the process (no hold exists here — the refusal is
       hold/wallet/confirmation/model independent by construction);
    3. BINDING: both import styles resolve to the blocked function — the
       module attribute, a deferred import (chat/service.py's style), and a
       post-patch module-level import (pipeline/routes/projects.py's own
       binding — the order the launcher's boot relies on).
    """
    import httpx

    from app.config import settings

    # 1 — fence (shrink the cap BEFORE arming, so the banner reads true;
    # the fence reads the module global at call time)
    globals()["MAX_MINIMAX_HTTP_REQUESTS"] = 3
    _install_fence()
    fired = 0

    def _mock(request):
        nonlocal fired
        fired += 1
        return httpx.Response(200, json={})

    probe = httpx.AsyncClient(transport=httpx.MockTransport(_mock))
    host = settings.minimax_base_url.split("//", 1)[-1].split("/")[0]
    await probe.post("https://other.invalid/")  # non-MiniMax host: not counted
    for _ in range(3):
        await probe.post(f"https://{host}/chat/completions", json={})
    assert fired == 4, fired
    try:
        await probe.post(f"https://{host}/chat/completions", json={})
        raise AssertionError("fence did not trip at the cap")
    except ProviderFenceTripped:
        pass
    assert fired == 4, f"fired past the cap: {fired}"
    await probe.aclose()
    print("[selftest] fence: MiniMax-scoped counting + pre-fire trip at the cap")

    # 2 — blocker
    blocked = _install_run_blocker()

    class _ExplodeOnTouch:
        def __getattr__(self, name):
            raise AssertionError(f"the blocked create_run read its input ({name})")

    try:
        await blocked(_ExplodeOnTouch(), _ExplodeOnTouch(), _ExplodeOnTouch())
        raise AssertionError("the blocked create_run did not refuse")
    except TestRunCreationBlocked:
        pass
    print("[selftest] blocker: refusal fires before any input is read — "
          "independent of hold / wallet / confirmation / model output")

    # 3 — binding
    from app.pipeline import orchestrator

    assert orchestrator.create_run is blocked
    from app.pipeline.orchestrator import create_run as via_deferred

    assert via_deferred is blocked
    # importlib: the routes package's __init__ shadows the submodule name
    # with the router object — import the module itself for the assertion.
    import importlib

    projects_routes = importlib.import_module("app.pipeline.routes.projects")
    assert projects_routes.create_run is blocked, (
        "the module-level import in routes/projects.py bound the REAL "
        "create_run — the launcher must patch BEFORE the app import"
    )
    print("[selftest] blocker binding: module attribute + deferred import + "
          "post-patch module-level import all resolve to the refusal")
    return 0


def _install_fence() -> None:
    import httpx

    from app.config import settings

    host_marker = settings.minimax_base_url.split("//", 1)[-1].split("/")[0]
    state = {"count": 0, "t0": time.monotonic()}
    real_post = httpx.AsyncClient.post
    real_stream = httpx.AsyncClient.stream

    def _fence(url: str) -> bool:
        """True when this call is a MiniMax call that is ALLOWED."""
        if host_marker not in str(url):
            return False
        if state["count"] >= MAX_MINIMAX_HTTP_REQUESTS:
            raise ProviderFenceTripped(
                f"MiniMax request budget exhausted ({MAX_MINIMAX_HTTP_REQUESTS})"
            )
        if time.monotonic() - state["t0"] > MAX_WALL_SECONDS:
            raise ProviderFenceTripped(
                f"wall-clock deadline exceeded ({MAX_WALL_SECONDS}s)"
            )
        state["count"] += 1
        print(f"[fence] minimax request #{state['count']}", flush=True)
        return True

    async def fenced_post(self, url, **kwargs):
        _fence(str(url))
        return await real_post(self, url, **kwargs)

    def fenced_stream(self, method, url, **kwargs):
        _fence(str(url))
        return real_stream(self, method, url, **kwargs)

    httpx.AsyncClient.post = fenced_post  # type: ignore[method-assign]
    httpx.AsyncClient.stream = fenced_stream  # type: ignore[method-assign]
    print(
        f"[fence] MiniMax-scoped request fence armed: host={host_marker} "
        f"cap={MAX_MINIMAX_HTTP_REQUESTS} deadline={MAX_WALL_SECONDS}s",
        flush=True,
    )


def main() -> None:
    if "--selftest" in sys.argv:
        import asyncio

        sys.exit(asyncio.run(_selftest()))
    _install_fence()
    _install_run_blocker()
    print("[blocker] create_run replaced with the test-instance refusal "
          "(this process only)", flush=True)
    import uvicorn

    from app.config import settings

    assert settings.film_edits_enabled, "gate flip failed"
    assert not settings.minimax_warmup_enabled, "warmup off failed"
    print(f"[gate-on] film_edits_enabled={settings.film_edits_enabled}", flush=True)
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        log_level="info",
        # no --reload: a file change mid-smoke must not restart the gate-on
        # process (the fence state and the prompt render are boot-time).
    )


if __name__ == "__main__":
    main()
