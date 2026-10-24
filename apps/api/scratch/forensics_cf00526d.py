"""forensics_cf00526d — the text-film deadlock incident's offline regression.

Read-only: pulls the incident conversation's pasted copy from the local DB
(project cf00526d-112c-4d3f-9028-ab28d83691ad, message seq 5), then drives
the REAL text-film chain offline (no LLM, no paid calls, no writes):

1. The manifest re-reads the full copy (whitespace-insensitive) and never
   severs a latin word at a line boundary (the incident's «Superhe|ro»).
2. The full-verbatim board (every line cited exactly once) assembles and
   validates CLEAN — the incident's L3/L7/L9/L12-class lines (8.5–9s) are
   legal scenes now that the 8s craft default is no longer a hard ceiling.
3. The SAME copy paces BOTH ways (2026-10-22 拍板 — 估计 = 建议非边界):
   no target = the reading estimate recommends ~101.5s; a named 20s = the
   user's explicit faster choice — a legal board (every line still cited,
   validator clean), with the pace note presented. The ~101.5s plan is A
   feasible arrangement, never the only legal one. The REAL refusals
   remain: a named 150s (over the render frame cap) and a named 0.5s (a
   scene would quantize to zero on the render grid).
4. An over-long copy fails the material preflight (film_text_beyond_reach)
   BEFORE any model call — the DEFAULT pace cannot stand past the frame
   cap; the message offers the faster-pace choice.

Run: uv run python -I scratch/forensics_cf00526d.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text as sql_text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.tools.film.storyboard import (  # noqa: E402
    CopyRef,
    FilmTextDirection,
    FilmTextSegment,
    FilmTextSource,
    _text_feasibility,
    assemble_text_storyboard,
    build_text_manifest,
    validate_storyboard,
)

PROJECT_ID = "cf00526d-112c-4d3f-9028-ab28d83691ad"


def _database_url() -> str:
    for line in Path("/Users/sylas/repurposer/.env").read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL not found in repo-root .env")


async def _incident_copy() -> str:
    eng = create_async_engine(_database_url())
    async with eng.connect() as c:
        content = (
            await c.execute(
                sql_text(
                    "select m.content from messages m "
                    "join conversations cv on cv.id = m.conversation_id "
                    "where cv.project_id = :p and m.seq = 5"
                ),
                {"p": PROJECT_ID},
            )
        ).scalar_one()
    await eng.dispose()
    text = content
    if text.startswith("这一段呢："):
        text = text[len("这一段呢：") :]
    text = text.strip()
    if text.startswith("“") and text.endswith("”"):
        text = text[1:-1]
    return text


def _alnum(ch: str) -> bool:
    return bool(re.match(r"[A-Za-z0-9]", ch))


async def main() -> int:
    copy = await _incident_copy()
    checks: list[tuple[str, bool, str]] = []

    lines = build_text_manifest(copy)
    preserved = "".join("".join(l.text for l in lines).split()) == "".join(
        copy.split()
    )
    checks.append(("full copy preserved (whitespace-insensitive)", preserved, ""))

    severed = [
        (l.id, l.text[-8:], lines[i + 1].text[:8])
        for i, l in enumerate(lines[:-1])
        if _alnum(l.text[-1]) and _alnum(lines[i + 1].text[0])
    ]
    checks.append(("no latin word severed at a line boundary", not severed, str(severed)))

    direction = FilmTextDirection(
        segments=[FilmTextSegment(refs=[CopyRef(line=l.id)]) for l in lines]
    )
    source = FilmTextSource(text=copy, verbatim=True)
    preflight = _text_feasibility(lines, source=source)
    checks.append(("feasibility preflight passes", preflight is None, str(preflight)))

    board, aviolations = assemble_text_storyboard(direction, lines, source=source)
    checks.append(("full-verbatim board assembles clean", board is not None and not aviolations, str([(v.code, v.detail[:60]) for v in aviolations])))
    if board is not None:
        vviolations = validate_storyboard(board, [], text_lines=lines)
        checks.append(("board validates clean", not vviolations, str([(v.code, v.detail[:60]) for v in vviolations])))
        over_default = max(s.seconds for s in board.scenes) > 8.0
        checks.append((
            f"long lines legally earn >8s windows (max {max(s.seconds for s in board.scenes):g}s, "
            f"total {sum(s.seconds for s in board.scenes):g}s, {len(board.scenes)} scenes)",
            over_default,
            "",
        ))

    src20 = FilmTextSource(text=copy, verbatim=True, target_seconds=20.0)
    pre = _text_feasibility(lines, source=src20)
    checks.append((
        "named 20s vs ~101.5s copy → preflight stands aside (explicit faster pace)",
        pre is None,
        str(pre.user_key if pre else None),
    ))
    b20, v20 = assemble_text_storyboard(direction, lines, source=src20)
    ok20 = (
        b20 is not None
        and not v20
        and abs(sum(s.seconds for s in b20.scenes) - 20.0) < 2.0
    )
    checks.append((
        f"named 20s produces a legal ~20s board ({sum(s.seconds for s in b20.scenes):g}s, "
        f"{len(b20.scenes)} scenes — every line still cited)"
        if b20 is not None else "named 20s produces a legal ~20s board",
        ok20,
        str([(v.code, v.detail[:60]) for v in v20]),
    ))
    if b20 is not None:
        vv20 = validate_storyboard(b20, [], text_lines=lines)
        checks.append(("the faster board validates clean", not vv20, str([(v.code, v.detail[:60]) for v in vv20])))
    from app.tools.film.storyboard import _text_source_note

    note = _text_source_note(src20)
    checks.append((
        "the presentation names the faster-than-estimate pace (never silent)",
        note is not None and "faster" in note,
        str(note),
    ))
    pre150 = _text_feasibility(
        lines, source=FilmTextSource(text=copy, verbatim=True, target_seconds=150.0)
    )
    checks.append((
        "named 150s → REAL frame-cap refusal (film_text_target_overflow)",
        pre150 is not None and pre150.user_key == "film_text_target_overflow",
        str(pre150.user_key if pre150 else None),
    ))
    b05, v05 = assemble_text_storyboard(
        direction, lines,
        source=FilmTextSource(text=copy, verbatim=True, target_seconds=0.5),
    )
    checks.append((
        "named 0.5s → REAL render-grid refusal (a scene would quantize to zero)",
        b05 is None and any("grid" in v.detail for v in v05),
        str([(v.code, v.detail[:60]) for v in v05]),
    ))

    inflated = copy * 6
    pre = _text_feasibility(
        build_text_manifest(inflated),
        source=FilmTextSource(text=inflated, verbatim=True),
    )
    checks.append((
        "over-long copy → pre-model film_text_beyond_reach",
        pre is not None and pre.user_key == "film_text_beyond_reach",
        str(pre.user_key if pre else None),
    ))

    ok = True
    for name, passed, detail in checks:
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not passed else ""))
    print(f"\n{'ALL CHECKS PASS' if ok else 'REGRESSIONS FOUND'} — {len(lines)} manifest lines from {len(copy)} chars")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
