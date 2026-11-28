"""Provider-neutral full LLM wire tracing.

The configured JSONL receives the complete request payload and the complete
response available at the provider boundary. Text and tool arguments are never
truncated or summarized. Credentials, signed URL queries and inline binary
media follow the existing local redaction/externalization rules.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import structlog

from app.config import settings

logger = structlog.get_logger()


def _trace_path() -> Path | None:
    raw = settings.llm_trace_path.strip()
    return Path(raw) if raw else None


def _trace_safe(value: Any, path: Path) -> Any:
    """Keep business payloads verbatim except credentials and inline bytes."""
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if key.lower() in {"authorization", "cookie", "api_key", "apikey", "token"}:
                safe[key] = "<redacted>"
            else:
                safe[key] = _trace_safe(item, path)
        return safe
    if isinstance(value, list):
        return [_trace_safe(item, path) for item in value]
    if isinstance(value, str):
        if value.startswith("data:") and ";base64," in value:
            header, encoded = value.split(",", 1)
            raw = base64.b64decode(encoded)
            digest = hashlib.sha256(raw).hexdigest()
            media_dir = path.parent / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            suffix = {"image/png": ".png", "image/jpeg": ".jpg", "video/mp4": ".mp4"}.get(
                header[5:].split(";", 1)[0], ".bin"
            )
            target = media_dir / f"{digest}{suffix}"
            if not target.exists():
                target.write_bytes(raw)
            return {"binary_ref": str(target), "sha256": digest, "bytes": len(raw)}
        if value.startswith(("https://", "http://")):
            parts = urlsplit(value)
            if parts.query:
                return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")) + "?<redacted-query>"
        return value
    return value


def _trace_write(record: dict[str, Any]) -> None:
    path = _trace_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_trace_safe(record, path), ensure_ascii=False) + "\n")
    except Exception:
        pass


def trace_payload_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    """Exact JSON/text sizes, not vendor token attribution or image-token guesses."""
    def measure(value: Any) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return {"json_chars": len(encoded.decode("utf-8")), "utf8_bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest()}

    messages = []
    for index, message in enumerate(payload.get("messages", [])):
        content = message.get("content")
        parts = []
        if isinstance(content, str):
            parts.append({"type": "text", "text_chars": len(content)})
        elif isinstance(content, list):
            for part in content:
                parts.append({"type": part.get("type"),
                              "text_chars": len(part.get("text", "")) if isinstance(part.get("text"), str) else 0})
        messages.append({"index": index, "role": message.get("role"),
                         "name": message.get("name"), "tool_call_id": message.get("tool_call_id"),
                         **measure(message), "parts": parts})
    tools = [{"name": tool.get("function", {}).get("name"), **measure(tool),
              "definition_count": len(tool.get("function", {}).get("parameters", {}).get("$defs", {}))}
             for tool in payload.get("tools", [])]
    return {"measurement": "compact JSON, ensure_ascii=False; sizes are not tokens",
            "payload": measure(payload),
            "top_level": {key: measure(value) for key, value in payload.items()},
            "messages": messages, "tools": tools}


def trace_start(payload: dict[str, Any], seat: str, *, provider: str, model: str) -> str:
    """Persist the exact payload passed to the provider, before transport."""
    call_id = str(uuid4())
    from app.metering import current_conversation_trace, current_model_prompt

    correlation = current_conversation_trace() or {}
    assembly = current_model_prompt()
    if assembly is not None:
        assembly["model_call_id"] = call_id
        assembly["provider"] = provider
        assembly["model"] = model
    from app.providers.llm.turn_trace import collector

    if active := collector():
        active.model_starts[call_id] = time.monotonic()
    inventory = trace_payload_inventory(payload) if _trace_path() is not None else None
    logger.info("model_request_started", model_call_id=call_id, seat=seat,
                provider=provider, model=model,
                agent=assembly.get("agent") if assembly else None,
                iteration=assembly.get("iteration") if assembly else None,
                **correlation, trace_path=str(_trace_path()) if _trace_path() else None,
                payload_inventory=inventory)
    _trace_write({
        "phase": "request",
        "model_call_id": call_id,
        "seat": seat,
        "provider": provider,
        "model": model,
        "started_at": datetime.now(UTC).isoformat(),
        **correlation,
        "inventory": inventory,
        "assembly": assembly,
        "payload": payload,
    })
    return call_id


def trace_argument_normalization(*, model_call_id, tool_call_id, agent, iteration, changes):
    if not changes:
        return
    from app.metering import current_conversation_trace
    record = {"phase": "arguments_normalized", "model_call_id": model_call_id,
              "tool_call_id": tool_call_id, "agent": agent, "iteration": iteration,
              "recorded_at": datetime.now(UTC).isoformat(),
              **(current_conversation_trace() or {}), "changes": changes}
    logger.info("tool_arguments_normalized", **record)
    if model_call_id is not None:
        _trace_write(record)


def trace_finish(call_id: str, *, provider: str, model: str,
                 response: Any = None, error: BaseException | None = None) -> None:
    """Persist the complete provider response before schema/argument parsing."""
    from app.metering import current_conversation_trace, current_model_prompt

    correlation = current_conversation_trace() or {}
    assembly = current_model_prompt()
    logger.info("model_request_finished", model_call_id=call_id,
                provider=provider, model=model, **correlation,
                iteration=assembly.get("iteration") if assembly else None,
                agent=assembly.get("agent") if assembly else None,
                outcome="response" if error is None else "error",
                usage=response.get("usage") if isinstance(response, dict) else None,
                error_type=type(error).__name__ if error is not None else None)
    _trace_write({
        "phase": "response" if error is None else "error",
        "model_call_id": call_id,
        "provider": provider,
        "model": model,
        "finished_at": datetime.now(UTC).isoformat(),
        **(current_conversation_trace() or {}),
        "response": response,
        "error": None if error is None else {"type": type(error).__name__, "message": str(error)},
    })

    from app.metering import _cached_tokens_of
    from app.providers.llm.turn_trace import collector, record_llm_exchange

    if active := collector():
        started = active.model_starts.pop(call_id, None)
        data = response if isinstance(response, dict) else {}
        usage = data.get("usage") or {}
        try:
            message = (data.get("choices") or [{}])[0].get("message") or data
            calls = [{"id": item.get("id"), "name": (item.get("function") or item).get("name")}
                     for item in message.get("tool_calls") or []]
            record_llm_exchange(
                iteration=assembly.get("iteration") if assembly else None, model_call_id=call_id,
                provider=provider, model=model, prompt_tokens=usage.get("prompt_tokens"),
                cached_tokens=_cached_tokens_of(usage), completion_tokens=usage.get("completion_tokens"),
                duration_ms=int((time.monotonic() - started) * 1000) if started is not None else None,
                tool_calls=calls, error={"type": type(error).__name__, "message": str(error)} if error else None,
            )
        except (AttributeError, TypeError, ValueError, IndexError, KeyError):
            pass
