"""Export recorded model wire payloads by project/conversation/turn/model-call ID.

Read-only: no model calls or project writes. Historical traces without project_id
are resolved through the existing conversations table. Per-section counts are
characters/bytes, never claimed to be vendor token counts.
"""
import argparse
import asyncio
import difflib
import json
import re
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.providers.llm.trace import trace_payload_inventory


def select_records(path: Path, identity: str, conversations: set[str]) -> list[dict]:
    selected = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except ValueError:
                # A concurrent append may leave just the last line incomplete.
                print(f"Skipping incomplete/invalid trace line {number}", file=sys.stderr)
                continue
            if identity in {row.get(k) for k in ("project_id", "conversation_id", "turn_id", "model_call_id")} or row.get("conversation_id") in conversations:
                selected.append(row)
    return selected


async def project_conversations(identity: str) -> set[str]:
    from sqlalchemy import select
    from app.models.database import AsyncSessionLocal, engine
    from app.models.tables import Conversation
    try:
        async with AsyncSessionLocal() as session:
            return {str(value) for value in await session.scalars(
                select(Conversation.id).where(Conversation.project_id == UUID(identity))
            )}
    finally:
        await engine.dispose()


def export_records(rows: list[dict], out: Path) -> str:
    out.mkdir(parents=True, exist_ok=True)
    by_call = {}
    for row in rows:
        by_call.setdefault(row["model_call_id"], []).append(row)
    lines = ["# Recorded model requests", "", "Token totals are provider-reported. Section sizes are exact compact-JSON characters/UTF-8 bytes of recorded content; they are not token attribution. Inline media is stored as binary_ref and URL queries are redacted. New request inventories measure the payload before this diagnostic substitution; historical inventories measure the recorded payload.", ""]
    previous_payload = None
    previous_call_id = None
    for call_id, records in by_call.items():
        folder = out / call_id
        folder.mkdir(exist_ok=True)
        request = next((r for r in records if r["phase"] == "request"), None)
        terminal = next((r for r in reversed(records) if r["phase"] in {"response", "error"}), None)
        for i, row in enumerate(records):
            (folder / f"{i:02d}-{row['phase']}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        lines += [f"## {call_id}", "", f"State: {terminal['phase'] if terminal else 'pending (no recorded response/error)'}; started: {request.get('started_at') if request else 'missing request'}", ""]
        if terminal:
            response = terminal.get("response") or {}
            lines += [f"Usage: `{json.dumps(response.get('usage'), ensure_ascii=False)}`", f"Error: `{json.dumps(terminal.get('error'), ensure_ascii=False)}`", ""]
        normalizations = [r for r in records if r["phase"] == "arguments_normalized"]
        if normalizations:
            lines += ["| Normalized argument | Original string | Number |", "|---|---|---|"]
            for event in normalizations:
                for change in event["changes"]:
                    lines.append(f"| `{change['path']}` | `{json.dumps(change['before'], ensure_ascii=False)}` | `{change['after']}` |")
            lines.append("")
        if not request:
            continue
        payload = request["payload"]
        assembly = request.get("assembly")
        if assembly is not None:
            (folder / "assembly.json").write_text(json.dumps(assembly, ensure_ascii=False, indent=2), encoding="utf-8")
            lines += [f"Agent: `{assembly.get('agent')}`; iteration: `{assembly.get('iteration', 'not supplied')}`; candidate retained: `{assembly.get('candidate_retained', 'not supplied')}`", "",
                      "[Assembly / rejection history / observation retention](" + call_id + "/assembly.json)", "",
                      "| Executed prompt source | SHA256 | Source text |", "|---|---|---|"]
            for kind in ("system_sources", "user_sources"):
                for index, source in enumerate(assembly.get(kind, [])):
                    filename = f"source-{kind}-{index:03d}.j2"
                    (folder / filename).write_text(source["text"], encoding="utf-8")
                    lines.append(f"| {source.get('path') or source.get('template')} | {source.get('sha256')} | [{filename}]({call_id}/{filename}) |")
            lines.append("")
        else:
            lines += ["Source provenance unavailable in this historical record; rendered messages below are the actual recorded input. Current files are not substituted as historical sources.", ""]
        if previous_payload is not None:
            before = json.dumps(previous_payload.get("messages", []), ensure_ascii=False, indent=2).splitlines(keepends=True)
            after = json.dumps(payload.get("messages", []), ensure_ascii=False, indent=2).splitlines(keepends=True)
            diff = "".join(difflib.unified_diff(before, after, fromfile=previous_call_id, tofile=call_id))
            (folder / "messages-diff.patch").write_text(diff, encoding="utf-8")
            lines += [f"[Actual message changes since previous request]({call_id}/messages-diff.patch)", ""]
        previous_payload = payload
        previous_call_id = call_id
        inventory = request.get("inventory") or trace_payload_inventory(payload)
        (folder / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
        lines += ["| Top-level field | JSON chars | UTF-8 bytes |", "|---|---:|---:|"]
        lines += [f"| {name} | {item['json_chars']} | {item['utf8_bytes']} |" for name, item in inventory["top_level"].items()]
        lines += ["", "| Message | Role / tool | JSON chars | Raw content |", "|---:|---|---:|---|"]
        for i, message in enumerate(payload.get("messages", [])):
            content = message.get("content", "")
            filename = f"message-{i:03d}.{'txt' if isinstance(content, str) else 'json'}"
            (folder / filename).write_text(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
            item = inventory["messages"][i]
            lines.append(f"| {i} | {message.get('role')} / {message.get('name', '')} | {item['json_chars']} | [{filename}]({call_id}/{filename}) |")
        lines += ["", "| Tool schema | JSON chars | Definitions |", "|---|---:|---:|"]
        for i, tool in enumerate(payload.get("tools", [])):
            name = tool.get("function", {}).get("name", str(i))
            safe_name = re.sub(r"[^\w.-]", "_", name)
            filename = f"tool-{i:03d}-{safe_name}.json"
            (folder / filename).write_text(json.dumps(tool, ensure_ascii=False, indent=2), encoding="utf-8")
            item = inventory["tools"][i]
            lines.append(f"| [{name}]({call_id}/{filename}) | {item['json_chars']} | {item['definition_count']} |")
        lines.append("")
    report = "\n".join(lines)
    (out / "index.md").write_text(report, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="Project, conversation, turn or model_call UUID")
    parser.add_argument("--trace", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    UUID(args.id)
    path = args.trace or (Path(settings.llm_trace_path) if settings.llm_trace_path else None)
    if path is None or not path.is_file():
        parser.error("Trace file missing; configure LLM_TRACE_PATH or pass --trace")
    rows = select_records(path, args.id, set())
    if not rows:
        rows = select_records(path, args.id, asyncio.run(project_conversations(args.id)))
    if not rows:
        parser.error("No recorded requests for this ID")
    export_records(rows, args.out)
    print(f"Exported {len({r['model_call_id'] for r in rows})} model calls: {args.out.resolve() / 'index.md'}")


if __name__ == "__main__":
    main()
