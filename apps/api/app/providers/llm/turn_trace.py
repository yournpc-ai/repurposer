"""Small per-turn diagnostics, scoped to the metered conversation and local trace path."""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app.metering import current_conversation_trace
from app.providers.llm.trace import _trace_path, _trace_safe


@dataclass
class _Collector:
    path: Path
    identity: dict
    started: float = field(default_factory=time.monotonic)
    iterations: int = 0
    model_starts: dict[str, float] = field(default_factory=dict)


_current: ContextVar[_Collector | None] = ContextVar("turn_trace", default=None)


def collector():
    identity = current_conversation_trace()
    root = _trace_path()
    if not identity or root is None:
        return None
    active = _current.get()
    if active is not None and active.identity is identity:
        return active
    conversation, turn = identity["conversation_id"], identity["turn_id"]
    if not all(re.fullmatch(r"[\w-]+", part) for part in (conversation, turn)):
        return None
    active = _Collector(root.parent / "turns" / conversation / f"{turn}.jsonl", identity)
    _current.set(active)
    return active


@asynccontextmanager
async def trace_loop():
    """Settle exceptions that bypass the normal ToolLoop result, including cancellation."""
    active = collector()
    try:
        yield
    except BaseException as exc:
        if active is not None:
            finalize_turn_trace(outcome=type(exc).__name__, total_iterations=active.iterations)
        raise


# Messages from an SDK or a tool can contain headers, URLs or media embedded
# in prose. Drop that string before applying the wire tracer's value redactor.
_sensitive = re.compile(
    r"authorization|bearer\s|cookie|(?:api[-_ ]?key|token|secret|password|credential|signature)"
    r"[\"'\s]*[:=]|\bsk-[\w-]+|https?://\S*[?@]|;base64,|[A-Za-z0-9+/]{96,}", re.I,
)


def _scrub(value):
    if isinstance(value, dict):
        return {k: "<redacted>" if re.search(r"api[-_]?key|token$|secret|password|cookie|authorization", k, re.I)
                else _scrub(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and _sensitive.search(value):
        return "<redacted>"
    return value


def _write(event, fields):
    active = collector()
    if active is None:
        return
    try:
        path = active.path
        path.parent.mkdir(parents=True, exist_ok=True)
        record = _trace_safe(_scrub({**active.identity, "event": event,
                                     "at": datetime.now(UTC).isoformat(), **fields}), path)
        line = json.dumps(record, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as out:
            out.write(line + "\n")
    except Exception:
        pass


def record_prompt_assembly(*, iteration, agent, template_files, context_sources, project_resources, offered_tools):
    _write("prompt_assembly", locals())


def record_llm_exchange(*, iteration, model_call_id, provider, model, prompt_tokens, cached_tokens,
                        completion_tokens, duration_ms, tool_calls, error=None):
    _write("llm_exchange", locals())


def record_tool_span(*, iteration, tool_call_id, tool_name, args_summary, duration_ms, ok,
                     produced_version=None, produced_output_id=None, sub_steps=None, error=None):
    _write("tool_span", locals())


def _markdown(events):
    summaries = [e for e in events if e["event"] == "turn_summary"]
    end = summaries[-1]
    lines = [f"# Turn {end['turn_id']}", ""]
    for key in ("conversation_id", "turn_id", "project_id", "outcome"):
        lines.append(f"- {key}: {end.get(key, '—')}")
    for key in ("duration_ms", "total_iterations"):
        lines.append(f"- {key}: {sum(s[key] for s in summaries)}")

    prompts = [e for e in events if e["event"] == "prompt_assembly"]
    files = dict.fromkeys(f for p in prompts for f in p["template_files"])
    lines += ["", "## Prompt & context", "", "- Templates / skills: " + (", ".join(files) or "—")]
    sizes = defaultdict(list)
    for prompt in prompts:
        for key, size in prompt["context_sources"].items():
            sizes[key].append(size)
    for key, values in sizes.items():
        span = str(min(values)) if min(values) == max(values) else f"{min(values)}–{max(values)}"
        lines.append(f"- {key}: {span} bytes")

    lines += ["", "## Project resources", ""]
    snapshots = [p["project_resources"] for p in prompts if p["project_resources"]]
    if snapshots:
        lines.append("First → last observed")
        for key in dict.fromkeys([*snapshots[0], *snapshots[-1]]):
            first, last = (json.dumps(s.get(key), ensure_ascii=False) for s in (snapshots[0], snapshots[-1]))
            lines.append(f"- {key}: {first}" + (f" → {last}" if first != last else ""))
    else:
        lines.append("No project snapshot observed.")

    lines += ["", "## Call flow", ""]
    previous = None
    for e in events:
        if e["event"] == "turn_summary":
            lines.append(f"- End: {e['outcome']} ({e['duration_ms']} ms)")
            previous = None
            continue
        iteration = e.get("iteration")
        if previous is None or iteration != previous or e["event"] == "prompt_assembly":
            lines.append(f"- iter {iteration if iteration is not None else '—'}")
        previous = iteration
        if e["event"] == "llm_exchange":
            calls = ", ".join(c["name"] for c in e["tool_calls"] if c.get("name"))
            lines.append(f"  - {e['model']}: prompt_tokens={e['prompt_tokens']}, cached_tokens={e['cached_tokens']}"
                         f" ({e['duration_ms']} ms)" + (f" → {calls}" if calls else ""))
        elif e["event"] == "tool_span":
            lines.append(f"  - {e['tool_name']} ({e['duration_ms']} ms): {'ok' if e['ok'] else 'failed'}")
            for key in ("produced_version", "produced_output_id", "sub_steps"):
                if e.get(key):
                    lines.append(f"    - {key}: {json.dumps(e[key], ensure_ascii=False)}")
        if e.get("error"):
            lines.append("    - " + json.dumps(e["error"], ensure_ascii=False))
    return "\n".join(lines) + "\n"


def finalize_turn_trace(*, outcome, total_iterations, credits_delta=None):
    active = collector()
    if active is None:
        return
    try:
        _write("turn_summary", {"outcome": outcome, "total_iterations": total_iterations,
                                "duration_ms": int((time.monotonic() - active.started) * 1000),
                                "credits_delta": credits_delta})
        # A resumed turn may already have events from an earlier worker/process.
        with active.path.open(encoding="utf-8") as source:
            events = []
            for line in source:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        markdown = _markdown(events)
        with TemporaryDirectory(dir=active.path.parent) as tmp:
            draft = Path(tmp) / "summary.md"
            draft.write_text(markdown, encoding="utf-8")
            draft.replace(active.path.with_suffix(".summary.md"))
    except Exception:
        pass
    finally:
        _current.set(None)
