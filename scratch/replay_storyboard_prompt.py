"""Replay the exact film_storyboarder prompt for project 309340c6.

Byte-accurate reconstruction: same code path the deferred seat runs
(load_storyboard_pages → build_line_manifest → page_prompt_dict → _assemble
→ jinja render + pack injection). Writes the user prompt to
scratch/replay_storyboard_prompt.md and prints size stats + the system line.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

NO_PROXY = "*"

from app.agents.base import jinja_env  # noqa: E402
from app.agents.contexts import pack_instructions  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Project  # noqa: E402
from app.tools.film.storyboard import (  # noqa: E402
    _assemble,
    build_line_manifest,
    film_storyboarder,
    load_storyboard_pages,
    page_prompt_dict,
)

PID = "309340c6-06e9-464d-8e8d-029feb10a912"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, PID)
        pages = await load_storyboard_pages(db, project)
    print(f"pages: {len(pages)}")
    lines = build_line_manifest(pages)
    print(f"manifest lines: {len(lines)}")
    for l in lines:
        print(f"  L{l.id} [p{l.page} {l.kind}] {l.text[:70]}")
    prompt_pages = [page_prompt_dict(p, i, lines) for i, p in enumerate(pages)]
    pending = project.pending_brief if isinstance(project.pending_brief, dict) else {}
    intent = pending.get("intent") or {}
    film_task = next(
        (t for t in (intent.get("tasks") or []) if t.get("tool") == "launch_film"),
        {},
    )
    kwargs, media = _assemble(
        prompt_pages,
        pending.get("prompt"),
        (film_task.get("params") or {}).get("focus"),
        (film_task.get("params") or {}).get("language"),
        [],  # media parts don't alter the text
    )
    kwargs["packs"] = pack_instructions(["launch-film"])
    user_prompt = jinja_env.get_template(film_storyboarder.prompt).render(**kwargs)
    out = Path(__file__).resolve().parents[1] / "scratch" / "replay_storyboard_prompt.md"
    out.write_text(user_prompt)
    print(f"\nsystem ({len(film_storyboarder.system)} chars):\n{film_storyboarder.system}")
    print(f"\nuser prompt: {len(user_prompt)} chars (~{len(user_prompt) // 4} tokens rough)")
    print(f"media parts: 3 screenshots (fold + 2 sub-pages) ride as image data URLs")
    print(f"written to {out}")


asyncio.run(main())
