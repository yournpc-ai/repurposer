"""Fenced runner for ``scripts/prompt_gate.py`` (the PAID pre-deploy gate).

prompt_gate itself carries no runaway guard: 10 probes × n rounds × ≤12
loop iterations, each logical call ≤3 HTTP attempts (tenacity / pre-emission
manual retries). This wrapper adds the missing fence WITHOUT touching the
gate script:

  - an ENFORCED request cap, computed STRUCTURALLY from the selected probes
    and ``--n`` (probes × n × 12 iterations × 3 attempts) — a trip raises
    ``ProviderFenceTripped`` BEFORE the request fires. The exception derives
    from BaseException on purpose: the gate tallies ``except Exception`` as
    provider errors (an INVALID reading), and a fence trip must never
    masquerade as one — it stops the run loudly instead;
  - a SESSION ledger (2026-10-21 授权口径): a cumulative cap across ALL
    invocations (probe + full + any rerun) persisted at
    ``/tmp/prompt_gate_fence_state.json`` — the per-process cap is
    min(structural, session-remaining), the spent count is written back at
    exit (a hard SIGKILL loses the in-run delta; Ctrl+C lands the finally).
    Restarting the script never refreshes the quota;
  - an outer cancellable deadline (``asyncio.wait_for``, ``--wall`` seconds)
    around the whole gate run: cancels the in-flight request with the run
    (the cleanup mechanism is proven by spike_tool_role_image.py --selftest
    leg C — same construction);
  - honest accounting at start and exit: the cap is the structural worst
    case (a runaway guard, NOT a tight budget); the EXPECTED logical-call
    count is an estimate and is printed as one.

Usage (from apps/api):
  uv run python scratch/run_prompt_gate_fenced.py -- --probe A --n 2
  uv run python scratch/run_prompt_gate_fenced.py --wall 7200 -- --n 12
"""

import asyncio
import json
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_API_ROOT))
sys.path.insert(0, str(_API_ROOT / "scripts"))

# prompt_gate's own constants (scripts/prompt_gate.py): the agent's
# max_iterations mirrors production at 12; each logical call ≤3 HTTP
# attempts (tenacity stop_after_attempt(3) / the streaming manual loop).
GATE_MAX_ITERATIONS = 12
MAX_ATTEMPTS_PER_CALL = 3
ALL_PROBES = ("A", "B", "C", "D", "E", "F", "G", "H", "H4", "I")

# The session ledger (2026-10-21 授权口径): 600 HTTP requests TOTAL across
# every invocation of this wrapper — the activity probe, the full run and
# any rerun share one budget. Hitting it stops the run and reports the gate
# INCOMPLETE; restarting the script never refreshes it.
SESSION_CAP = 600
SESSION_STATE = Path("/tmp/prompt_gate_fence_state.json")


class ProviderFenceTripped(BaseException):  # noqa: N818
    """The fence's refusal. BaseException, deliberately: the gate's per-call
    ``except Exception`` tallies provider errors into an INVALID reading —
    a fence trip is not a provider event, it is the run's stop signal."""


REQUESTS: list[str] = []


def _install_fence(max_requests: int) -> None:
    import httpx

    from app.config import settings

    host_marker = settings.minimax_base_url.split("//", 1)[-1].split("/")[0]
    real_post = httpx.AsyncClient.post
    real_stream = httpx.AsyncClient.stream

    def _fence(url: str) -> None:
        if host_marker not in str(url):
            return
        if len(REQUESTS) >= max_requests:
            raise ProviderFenceTripped(
                f"prompt_gate request budget exhausted ({max_requests} — "
                "the structural cap; a runaway loop fired it)"
            )
        REQUESTS.append(str(url))
        print(f"[fence] minimax request #{len(REQUESTS)}", flush=True)

    async def fenced_post(self, url, **kwargs):
        _fence(str(url))
        return await real_post(self, url, **kwargs)

    def fenced_stream(self, method, url, **kwargs):
        _fence(str(url))
        return real_stream(self, method, url, **kwargs)

    httpx.AsyncClient.post = fenced_post  # type: ignore[method-assign]
    httpx.AsyncClient.stream = fenced_stream  # type: ignore[method-assign]
    print(f"[fence] MiniMax-scoped fence armed: host={host_marker} "
          f"cap={max_requests} (structural worst case)", flush=True)


def main() -> int:
    # Peel the wrapper's own flags; everything else passes through to the
    # gate's own argparse verbatim.
    argv = list(sys.argv[1:])
    wall = 7200.0
    if "--wall" in argv:
        i = argv.index("--wall")
        wall = float(argv[i + 1])
        del argv[i : i + 2]
    if argv and argv[0] == "--":
        argv = argv[1:]
    sys.argv = [sys.argv[0], *argv]

    probe = None
    n = 12
    if "--probe" in argv:
        probe = argv[argv.index("--probe") + 1]
    if "--n" in argv:
        n = int(argv[argv.index("--n") + 1])
    probes = 1 if probe else len(ALL_PROBES)
    # STRUCTURAL cap: every round of every probe burning every iteration,
    # each retrying the transport maximum. Expected actuals are FAR below
    # (≈2 iterations per round) — printed as an estimate, never as a cap.
    structural = probes * n * GATE_MAX_ITERATIONS * MAX_ATTEMPTS_PER_CALL
    spent = 0
    if SESSION_STATE.exists():
        try:
            spent = int(json.loads(SESSION_STATE.read_text()).get("spent", 0))
        except (ValueError, json.JSONDecodeError):
            spent = 0
    remaining = SESSION_CAP - spent
    cap = min(structural, remaining)
    print(f"[fence] scope: probes={probe or 'ALL'} n={n} → structural HTTP "
          f"cap {structural}; session ledger {spent}/{SESSION_CAP} spent → "
          f"effective cap {cap}; expected logical calls ≈ {probes * n * 2} "
          f"(ESTIMATE, not enforced); wall {wall}s (cancellable)", flush=True)
    if remaining <= 0:
        print(f"[fence] session budget exhausted ({SESSION_CAP} across all "
              "invocations) — refusing to run; report the gate INCOMPLETE.",
              file=sys.stderr)
        return 2

    _install_fence(cap)

    import prompt_gate

    async def _run() -> int:
        return await asyncio.wait_for(prompt_gate.main(), timeout=wall)

    rc = 2
    try:
        rc = asyncio.run(_run())
        return rc
    except TimeoutError:
        print(f"[fence] OUTER DEADLINE: gate exceeded {wall}s — cancelled "
              "(the in-flight request cancelled with it)", file=sys.stderr)
        return 2
    except ProviderFenceTripped as e:
        print(f"[fence] TRIPPED: {e}", file=sys.stderr)
        return 2
    finally:
        total = spent + len(REQUESTS)
        SESSION_STATE.write_text(json.dumps({"spent": total}))
        print(f"[fence] actual MiniMax HTTP requests this run: "
              f"{len(REQUESTS)} (cap was {cap}); session ledger now "
              f"{total}/{SESSION_CAP}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
