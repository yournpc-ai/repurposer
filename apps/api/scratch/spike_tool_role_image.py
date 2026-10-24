"""R3 spike: does MiniMax accept AND see image parts on a role:tool message?

The question the R3 read seat (ToolObservation.images → the loop's
_observation_wire_content → content parts on the role:tool message) cannot
answer locally: whether the provider (minimax-m3 @ settings.minimax_base_url)
accepts tool-role content parts, and whether the model actually READS the
image (a 200 with a wrong answer = accepted-but-blind, not supported).

Production path under test (nothing re-implemented here):
  ToolLoopAgent.call_loop  (real message assembly + observation tail)
  → _observation_wire_content  (real parts projection)
  → MiniMaxClient.generate_stream_with_tools / generate_with_tools  (real wire)

Cases (each an independent loop run, fresh agent registration):
  C0  control, NO image in the observation — the code word must be
      UNKNOWABLE (proves the word never leaks through text).
  C1  the spike: image rides the role:tool message as content parts.
      PASS = the final answer carries the exact code word (pixel-only
      fact). The verdict reads BOTH report channels — the terminal call's
      ``findings`` argument AND the prose (a tool-call-only interface makes
      the arguments channel the model's natural report seat: the first live
      run proved content comes back empty while the findings rode the
      arguments).
  C2  user-role image control (agents/base.py _user_message — the director's
      verified media form): proves model+key+image pipeline works today, so
      a C1 failure isolates "tool role" as the only variable.

Anti-cheat: the code word is randomized per run and appears ONLY in the
image pixels — never in any message text, caption, or this file's logs
(until the verdict print). A correct C1 answer is obtainable only by
reading pixels.

Instrumentation: the shared httpx client's post/stream are wrapped to count
ACTUAL HTTP requests (tenacity retries included); usage dicts are captured
at the _log_usage seam. No production code is modified — both hooks are
in-process monkeypatches of observation points, never of serialization.

Usage:
  uv run python scratch/spike_tool_role_image.py --dry       # shapes only, free
  uv run python scratch/spike_tool_role_image.py --selftest  # fence proof, free
  uv run python scratch/spike_tool_role_image.py             # LIVE (paid, ~¢)

Enforced limits (the fence, not an estimate): ≤30 HTTP requests (a
conservative cap over the structural worst case: 2 loop cases × ≤3
iterations + the C2 single-shot = ≤7 logical calls, each ≤3 transport
attempts → ≤21), checked BEFORE a request
fires — a trip refuses the send. The 600s wall is enforced at TWO seats: the
same pre-send check in the fence, PLUS an outer ``asyncio.wait_for`` deadline
around the whole live run that CANCELS the in-flight request (cleanup proven
by --selftest). What the fence never does: cancel an in-flight request by
itself (a pre-send check cannot) — that is the outer deadline's job.
Expected actuals ≈ 5 requests. Output length is NOT capped by a parameter
(the client carries no max_tokens knob) — answers are naturally short.
"""

import argparse
import asyncio
import base64
import io
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import DictLoader, Environment  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.agents import tool_loop as tl  # noqa: E402
from app.agents.base import _user_message  # noqa: E402
from app.agents.tool_loop import ChatTool, ToolLoopAgent, ToolObservation  # noqa: E402
from app.config import settings  # noqa: E402
from app.models.schemas import MediaInput, MediaInputType  # noqa: E402
from app.providers.llm import minimax as minimax_mod  # noqa: E402
from app.providers.llm.base import ToolCall, ToolGeneration  # noqa: E402
from app.providers.llm.minimax import MiniMaxClient  # noqa: E402

# ---------------------------------------------------------------------------
# instrumentation + request fence (observation only — serialization untouched)
# ---------------------------------------------------------------------------
#
# The fence is the ENFORCED limit (not an estimate): it wraps the shared
# httpx pool client and REFUSES any call past the caps by raising
# ProviderFenceTripped BEFORE the request fires. Retry-layer safety:
# ProviderFenceTripped is neither an httpx.TransportError nor an LLMError,
# so the streaming path's `except (TransportError, LLMError)` never catches
# it; tenacity's `retry_if_not_exception_type(LLMSchemaError)` DOES re-enter
# the wrapped function, but every re-entry trips the fence again BEFORE
# firing — zero requests past the cap either way (proven by --selftest).

class ProviderFenceTripped(RuntimeError):
    """The request fence's refusal — deliberately outside the LLMError /
    TransportError classes so no retry layer mistakes it for a hiccup."""


REQUESTS: list[dict] = []
USAGES: list[dict] = []
# Fence trip ledger (the selftest's assertion substrate): one entry per
# refusal — "count" / "wall". A retry layer that re-enters shows up here as
# additional trips; a layer that FIRES past the cap shows up in REQUESTS.
TRIPS: list[str] = []

# Hard caps (enforced). Accounting, layers separated:
#   - logical client calls = the TWO loop cases (C0/C1, max_iterations=3
#     each → ≤6) + the C2 single-shot (1) → at most 7;
#   - HTTP requests ≤ 3 per logical call (tenacity on the plain variant /
#     pre-emission manual retries on the streaming variant) → ≤21 worst;
#     the cap 30 stands as the conservative fence above that worst case.
# Expected actuals: 5 logical calls, 5 HTTP requests.
MAX_HTTP_REQUESTS = 30
MAX_WALL_SECONDS = 600.0


def _instrument() -> None:
    """Count actual HTTP requests on the shared pool client, fence beyond the
    caps, and capture the usage dicts (the module's _log_usage seam) —
    payload shapes are logged as SIZES only (content never prints)."""
    pool_client = minimax_mod._shared_client()
    real_post = pool_client.post
    real_stream = pool_client.stream
    t0 = time.monotonic()

    def _fence() -> None:
        if len(REQUESTS) >= MAX_HTTP_REQUESTS:
            TRIPS.append("count")
            raise ProviderFenceTripped(
                f"request budget exhausted ({MAX_HTTP_REQUESTS})"
            )
        if time.monotonic() - t0 > MAX_WALL_SECONDS:
            TRIPS.append("wall")
            raise ProviderFenceTripped(
                f"wall-clock deadline exceeded ({MAX_WALL_SECONDS}s)"
            )

    async def fenced_post(url, **kwargs):
        _fence()
        payload = kwargs.get("json") or {}
        REQUESTS.append(
            {
                "kind": "post",
                "stream": bool(payload.get("stream")),
                "payload_bytes": len(json.dumps(payload)),
                "messages": len(payload.get("messages") or []),
            }
        )
        return await real_post(url, **kwargs)

    def fenced_stream(method, url, **kwargs):
        _fence()
        payload = kwargs.get("json") or {}
        REQUESTS.append(
            {
                "kind": "stream",
                "payload_bytes": len(json.dumps(payload)),
                "messages": len(payload.get("messages") or []),
            }
        )
        return real_stream(method, url, **kwargs)

    pool_client.post = fenced_post  # type: ignore[method-assign]
    pool_client.stream = fenced_stream  # type: ignore[method-assign]
    minimax_mod._log_usage = lambda usage: USAGES.append(dict(usage or {}))


# ---------------------------------------------------------------------------
# probe image — pixel-only facts, randomized per run
# ---------------------------------------------------------------------------

_ADJECTIVES = ["MARLIN", "QUARTZ", "FALCON", "BIRCH", "COPPER", "IVORY"]


def _probe_image(code_word: str) -> str:
    """640x360 JPEG data URL: a code word + a red square + seven ovals on a
    deep-blue field. The word is rendered ONLY here."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (640, 360), (24, 60, 110))
    d = ImageDraw.Draw(img)
    d.rectangle([30, 60, 170, 200], fill=(210, 60, 60))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 44)
        sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 34)
    except OSError:
        font = sub = ImageFont.load_default()
    d.text((195, 105), code_word, font=font, fill=(255, 255, 255))
    d.text((40, 270), "seven ovals", font=sub, fill=(240, 220, 120))
    for i in range(7):
        d.ellipse([320 + i * 44, 265, 350 + i * 44, 315], outline=(255, 255, 255), width=3)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# the loop rig
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a read-back probe. The user asks about an image that a tool "
    "result may carry. ALWAYS call the read tool first. After the tool "
    "result arrives, call the answer tool with your findings. Never invent "
    "image content: if no image is visible to you, say exactly NO IMAGE "
    "VISIBLE. When you can see an image, report the code word it prints "
    "and its background color."
)

_USER_MSG = (
    "Call read_probe, then answer: (1) the exact code word printed in the "
    "image, (2) the image's background color. If you cannot see any image, "
    "say NO IMAGE VISIBLE."
)


class _AnswerArgs(BaseModel):
    """The terminal call's report channel (read-tolerant: an empty findings
    still validates — a model that speaks in prose instead never gets
    spuriously rejected)."""

    findings: str = ""


def _agent(name: str, client=None) -> ToolLoopAgent:
    read = ChatTool(
        name="read_probe",
        description="Read the probe view. Returns facts and possibly one image.",
        params_model=None,
        terminal=False,
    )
    # The terminal tool carries a findings FIELD: a tool-call-only interface
    # makes the arguments channel the model's natural report seat (the first
    # live run proved content comes back empty — the findings rode the
    # arguments the probe wasn't reading). The verdict reads BOTH channels.
    answer = ChatTool(
        name="answer",
        description="End the turn — put your findings in the findings field.",
        params_model=_AnswerArgs,
        terminal=True,
    )
    return ToolLoopAgent(
        name=name,
        prompt="spike_user.j2",
        system=_SYSTEM,
        assemble=lambda **kw: ({"message": kw["message"]}, []),
        tools=[read, answer],
        temperature=0.0,
        # 3 iterations: read → answer + one recovery. The production chat
        # agents carry 12; the probe journey needs two, so the fence stays
        # tight (上限纪律: caps are what the journey needs, no more).
        max_iterations=3,
        client=client,
    )


async def _run_case(
    label: str, *, with_image: bool, code_word: str, dry: bool
) -> dict:
    """One loop case. Returns the verdict record."""
    data_url = _probe_image(code_word)
    images: tuple = ()
    if with_image:
        images = (
            MediaInput(
                type=MediaInputType.IMAGE,
                mime="image/jpeg",
                data_url=data_url,
                # caption binds the view but NEVER hints at its content
                caption='page 0 · shot 0 "(top)" · probe.local',
            ),
        )

    captured: dict = {}

    async def execute(name, params, prose):
        if name == "read_probe":
            return ToolObservation(
                "Probe view facts: one captured view of the test page.",
                images=images,
            )
        captured["findings"] = getattr(params, "findings", "") if params else ""
        return None  # answer = terminal accept

    if dry:
        # Assemble the wire shape without any client call: the loop runs
        # against a stub client that records the messages it receives and
        # closes on the terminal answer.
        recorded: list[list[dict]] = []

        class _Stub:
            capabilities = type("Caps", (), {"supports_native_tools": True})()

            def _reply(self, messages):
                recorded.append(messages)
                # The observation tail landed → close with the terminal call.
                if any(m.get("role") == "tool" for m in messages):
                    return ToolGeneration(
                        content="done",
                        tool_calls=[ToolCall(id="c1", name="answer", arguments={})],
                    )
                return ToolGeneration(
                    content="let me read",
                    tool_calls=[ToolCall(id="c0", name="read_probe", arguments={})],
                )

            async def generate_stream_with_tools(self, messages, **kw):
                return self._reply(messages)

            async def generate_with_tools(self, messages, **kw):
                return self._reply(messages)

        agent = _agent(f"spike_dry_{label}", client=_Stub())  # type: ignore[arg-type]
        await agent.call_loop(execute, message=_USER_MSG, on_delta=lambda t: None)
        tool_msg = recorded[-1][-1]
        content = tool_msg["content"]
        summary = []
        if isinstance(content, str):
            summary.append(f"text:{len(content)}ch")
        else:
            for part in content:
                if part["type"] == "text":
                    summary.append(f"text:{len(part['text'])}ch")
                else:
                    key = f"{part['type'].split('_')[0]}_url"
                    summary.append(f"{part['type']}:{len(part[key]['url'])}ch")
        print(f"[dry {label}] iterations={len(recorded)} "
              f"roles={[m['role'] for m in recorded[-1]]} tool-msg parts: {summary}")
        return {"case": label, "dry": True, "parts": summary}

    agent = _agent(f"spike_live_{label}_{int(time.time() * 1000)}")
    result = await agent.call_loop(execute, message=_USER_MSG, on_delta=lambda t: None)
    prose = result.prose or ""
    findings = captured.get("findings") or ""
    report = f"{findings}\n{prose}"
    return {
        "case": label,
        "iterations": result.iterations,
        "calls": result.calls,
        "code_word_found": code_word in report,
        "no_image_admitted": "NO IMAGE VISIBLE" in report.upper(),
        "findings": findings[-300:],
        "prose_tail": prose[-300:],
    }


async def _run_user_role_control(code_word: str) -> dict:
    """C2: the director's verified media form — image parts on the USER
    message (agents/base.py _user_message), one plain generate_with_tools."""
    media = [
        MediaInput(
            type=MediaInputType.IMAGE,
            mime="image/jpeg",
            data_url=_probe_image(code_word),
            caption="the probe view",
        )
    ]
    messages = [
        {"role": "system", "content": _SYSTEM},
        _user_message(
            _USER_MSG.replace("Call read_probe, then answer", "Answer"), media
        ),
    ]
    client = MiniMaxClient()
    result = await client.generate_with_tools(
        messages=messages,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "answer",
                    "description": "End the turn — put your findings in the "
                                   "findings field.",
                    "parameters": {
                        "type": "object",
                        "properties": {"findings": {"type": "string"}},
                    },
                },
            }
        ],
        temperature=0.0,
    )
    prose = result.content or ""
    findings = ""
    if result.tool_calls:
        args = result.tool_calls[0].arguments
        if isinstance(args, dict):
            findings = str(args.get("findings") or "")
    report = f"{findings}\n{prose}"
    return {
        "case": "C2_user_role_image",
        "code_word_found": code_word in report,
        "no_image_admitted": "NO IMAGE VISIBLE" in report.upper(),
        "findings": findings[-300:],
        "prose_tail": prose[-300:],
    }


async def _selftest() -> int:
    """FREE fence proof (no provider). Four legs, each asserting what it
    ACTUALLY executes (the report never outruns the evidence):

    (C) the outer deadline's cleanup: a stuck in-flight request under
        ``asyncio.wait_for`` is cancelled — the CancelledError lands inside
        the transport stub (the mechanism the live run's outer timeout
        relies on);
    (A) the request cap: the fence trips at the cap and ZERO requests fire
        past it;
    (B1) streaming-path propagation: with the fence exhausted, the REAL
        ToolLoopAgent.call_loop (real MiniMaxClient, real
        generate_stream_with_tools) trips on its first streaming attempt —
        ProviderFenceTripped escapes the loop untouched (the retry guard's
        ``except (TransportError, LLMError)`` never sees it: exactly ONE
        trip, no re-entry) and the loop issues no further requests;
    (B2) tenacity re-entry: the REAL ``generate_with_tools`` under an
        exhausted fence trips once per tenacity attempt (3 trips) and
        re-raises ProviderFenceTripped — re-entries re-trip BEFORE firing,
        zero requests past the cap.
    """
    fired = 0
    state = {"mode": "answer", "cancelled": False}

    pool_client = minimax_mod._shared_client()

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "ok", "tool_calls": [
                    {"id": "c", "function": {"name": "answer", "arguments": "{}"}}
                ]}, "finish_reason": "tool_calls"}],
                "usage": {},
            }

        def raise_for_status(self):
            return None

    async def fake_post(url, **kwargs):
        nonlocal fired
        fired += 1
        if state["mode"] == "block":
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                state["cancelled"] = True
                raise
        return _Resp()

    def fake_stream(method, url, **kwargs):  # the fence must trip first
        raise AssertionError("the fence let a stream call reach the transport")

    pool_client.post = fake_post  # type: ignore[method-assign]
    pool_client.stream = fake_stream  # type: ignore[method-assign]
    _instrument()  # wraps the fakes with the fence (single wrap)

    # (C) the outer deadline cancels an in-flight request (cleanup proof)
    state["mode"] = "block"
    try:
        await asyncio.wait_for(
            pool_client.post("https://probe.invalid/", json={}), timeout=0.3
        )
        raise AssertionError("the stuck request returned")
    except TimeoutError:
        pass
    assert state["cancelled"], "the in-flight request was NOT cancelled"
    assert len(REQUESTS) == 1 and fired == 1
    print("[selftest] outer deadline: in-flight request cancelled at the "
          "timeout (cleanup verified)")
    REQUESTS.clear()
    TRIPS.clear()
    fired = 0
    state["mode"] = "answer"

    # (A) the request cap: fire to the cap, then refuse WITHOUT firing
    for _ in range(MAX_HTTP_REQUESTS):
        await pool_client.post("https://probe.invalid/", json={})
    assert fired == MAX_HTTP_REQUESTS, fired
    try:
        await pool_client.post("https://probe.invalid/", json={})
        raise AssertionError("fence did not trip")
    except ProviderFenceTripped:
        pass
    assert fired == MAX_HTTP_REQUESTS, f"request fired past the cap: {fired}"
    assert TRIPS == ["count"], TRIPS
    print(f"[selftest] cap: fence trips at {MAX_HTTP_REQUESTS}; zero requests past it")
    # REQUESTS stays AT the cap — legs B1/B2 exercise a fully-tripped fence.

    # The spike's user template lives in-process (DictLoader) — the loop
    # legs below run the REAL call_loop, which renders it.
    tl.jinja_env = Environment(loader=DictLoader({"spike_user.j2": "{{ message }}"}))

    # (B1) streaming-path propagation through the REAL loop
    async def _unused_execute(*a):  # never reached — the fence trips first
        return None

    agent = _agent(
        "spike_selftest_b1", client=MiniMaxClient(api_key="selftest")
    )
    trips_before = len(TRIPS)
    try:
        await agent.call_loop(
            _unused_execute, message=_USER_MSG, on_delta=lambda t: None
        )
        raise AssertionError("the loop ran past an exhausted fence")
    except ProviderFenceTripped:
        pass
    assert len(TRIPS) - trips_before == 1, (
        f"streaming path re-entered after the trip: {TRIPS[trips_before:]}"
    )
    assert fired == MAX_HTTP_REQUESTS and len(REQUESTS) == MAX_HTTP_REQUESTS
    print("[selftest] streaming path: the trip escapes the loop on the first "
          "attempt (no retry swallow), zero further requests")

    # (B2) tenacity re-entry re-trips before firing (the plain variant)
    client = MiniMaxClient(api_key="selftest")
    trips_before = len(TRIPS)
    try:
        await client.generate_with_tools(
            messages=[{"role": "user", "content": "x"}],
            tools=[{
                "type": "function",
                "function": {"name": "answer", "description": "x",
                             "parameters": {"type": "object", "properties": {}}},
            }],
        )
        raise AssertionError("generate_with_tools ran past an exhausted fence")
    except ProviderFenceTripped:
        pass
    assert len(TRIPS) - trips_before == 3, (
        f"tenacity attempts ≠ 3 trips: {TRIPS[trips_before:]}"
    )
    assert fired == MAX_HTTP_REQUESTS and len(REQUESTS) == MAX_HTTP_REQUESTS
    print("[selftest] tenacity path: 3 re-entries, 3 pre-fire re-trips, "
          "ProviderFenceTripped re-raised, zero requests past the cap")
    return 0


async def _run_cases(args, code_word: str) -> list[dict]:
    """The case block (dry shapes or live calls), one invocation per case."""
    verdicts: list[dict] = []
    if args.only in (None, "C0"):
        verdicts.append(
            await _run_case("C0_no_image_control", with_image=False,
                            code_word=code_word, dry=args.dry)
        )
    if args.only in (None, "C1"):
        verdicts.append(
            await _run_case("C1_tool_role_image", with_image=True,
                            code_word=code_word, dry=args.dry)
        )
    if args.only in (None, "C2"):
        if args.dry:
            media = [MediaInput(type=MediaInputType.IMAGE, mime="image/jpeg",
                                data_url=_probe_image(code_word), caption="x")]
            msg = _user_message(_USER_MSG, media)
            parts = [p["type"] for p in msg["content"]]
            print(f"[dry C2] user msg parts: {parts}")
            verdicts.append({"case": "C2_user_role_image", "dry": True})
        else:
            verdicts.append(await _run_user_role_control(code_word))
    return verdicts


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="shapes only, no provider call")
    parser.add_argument("--selftest", action="store_true", help="fence proof, no provider call")
    parser.add_argument(
        "--only", choices=["C0", "C1", "C2"], default=None, help="run one case"
    )
    args = parser.parse_args()

    if args.selftest:
        return await _selftest()

    if not args.dry and not settings.minimax_api_key:
        print("MINIMAX_API_KEY not configured", file=sys.stderr)
        return 2

    # The spike's user template lives in-process (DictLoader) — the prompts
    # tree is untouched; everything PAST the template lookup is the
    # production serialization path byte for byte.
    tl.jinja_env = Environment(loader=DictLoader({"spike_user.j2": "{{ message }}"}))

    code_word = f"{random.choice(_ADJECTIVES)}-{random.randint(1000, 9999)}"
    print(f"provider: {settings.minimax_model} @ {settings.minimax_base_url}")
    print(f"code word (kept out of every message): {code_word}")

    if not args.dry:
        _instrument()

    verdicts: list[dict] = []
    t0 = time.monotonic()
    try:
        if args.dry:
            verdicts = await _run_cases(args, code_word)
        else:
            # The outer deadline (the fence's wall-check twin): cancels the
            # run — AND its in-flight request — at the wall (--selftest leg
            # C proves the cancellation cleanup).
            verdicts = await asyncio.wait_for(
                _run_cases(args, code_word), timeout=MAX_WALL_SECONDS
            )
    except TimeoutError:
        print(f"\nOUTER DEADLINE: the run exceeded {MAX_WALL_SECONDS}s and "
              "was cancelled (the in-flight request cancelled with it)")
        verdicts.append({"case": "timeout",
                         "error": f"outer deadline {MAX_WALL_SECONDS}s"})
    except Exception as e:
        print(f"\nPROVIDER/WIRE ERROR: {type(e).__name__}: {str(e)[:500]}")
        verdicts.append({"case": "error", "error": f"{type(e).__name__}: {str(e)[:300]}"})

    elapsed = time.monotonic() - t0
    print("\n=== verdicts ===")
    for v in verdicts:
        print(json.dumps(v, ensure_ascii=False))
    print(f"\nactual HTTP requests: {len(REQUESTS)}")
    for r in REQUESTS:
        print(f"  {r}")
    print(f"usage records: {len(USAGES)}")
    for u in USAGES:
        print(f"  {u}")
    print(f"elapsed: {elapsed:.1f}s")

    if args.dry:
        return 0
    c0 = next((v for v in verdicts if v.get("case") == "C0_no_image_control"), None)
    c1 = next((v for v in verdicts if v.get("case") == "C1_tool_role_image"), None)
    c2 = next((v for v in verdicts if v.get("case") == "C2_user_role_image"), None)
    print("\n=== verdict summary ===")
    if c1 and c1.get("code_word_found") and c0 and not c0.get("code_word_found"):
        print("POSITIVE: the model read the code word off the tool-role image "
              "(and could not know it without the image). Option A stands.")
        return 0
    if c1 and c1.get("no_image_admitted"):
        print("NEGATIVE (content-blind): the request was accepted but the model "
              "could not see the tool-role image. Fallback (synthetic user "
              "message) is the designed answer — C2 confirms the pipeline:")
        print(f"  C2 user-role control saw the image: "
              f"{bool(c2 and c2.get('code_word_found'))}")
        return 1
    if c1 and not c1.get("code_word_found") and c2 and c2.get("code_word_found"):
        print("NEGATIVE (wrong answer on tool-role, correct on user-role): "
              "the tool-role image does not reach the model's vision. "
              "Fallback indicated.")
        return 1
    print("INCONCLUSIVE — read the verdicts above (a wrong answer on BOTH "
          "image cases suggests a vision-capability or image-quality issue, "
          "not a wire-shape issue).")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
