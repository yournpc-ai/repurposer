"""Import or generate curated MiniMax Music 3.0 library tracks.

The positional argument is the local directory containing rendered MP3 files
named ``<mood>.mp3`` (e.g. ``apps/api/assets/music/vlog-nagoya-citypop.mp3``).
Each MP3 is decoded with PyAV, hashed, and uploaded under the deterministic
music object key; startup reconcile (or ``--reconcile``) populates the DB rows
with BeatGrid, LUFS, waveform peaks, and section timestamps.

Existing objects are reused only when their bytes match the local file; a
mismatch fails loudly unless ``--overwrite`` is explicitly passed.

Usage (from apps/api/):
    # Export all 16 MiniMax Music 3.0 generation prompts (JSON + Markdown):
    uv run python scripts/import_library_music.py --export-prompts assets/music

    # Generate missing tracks via MiniMax Music 3.0 API (requires paying key):
    uv run python scripts/import_library_music.py assets/music --generate

    # Import all present MP3 files in assets/music/ to object storage & reconcile DB:
    uv run python scripts/import_library_music.py assets/music --reconcile
    uv run python scripts/import_library_music.py assets/music --mood vlog-nagoya-citypop
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.music import (  # noqa: E402
    AUDIO_EXT,
    CURATED_MUSIC_CATALOG,
    USER_MODEL,
    CuratedMusicAudio,
    CuratedMusicEntry,
    default_music_id,
    generate_music,
    music_disk_path,
    music_file_path,
    persist_music,
    probe_music_duration_seconds,
    seed_default_music,
)
from app.providers.storage import read  # noqa: E402


def _export_prompts(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "mood": e["mood"],
            "filename": e["original_filename"],
            "title": e["title"],
            "title_zh": e["title_zh"],
            "category": e["category"],
            "format_kind": e["format_kind"],
            "style": e["style"],
            "bpm": e["reference_bpm"],
            "target_duration_seconds": e["target_duration_seconds"],
            "energy": e["energy"],
            "is_instrumental": True,
            "model": USER_MODEL,
            "prompt": e["generation_prompt"],
        }
        for e in CURATED_MUSIC_CATALOG
    ]
    json_path = out_dir / "music3_prompts.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Rookie Studio · MiniMax Music 3.0 旗舰曲库（16 首生成清单）",
        "",
        "使用 [MiniMax Audio](https://www.minimax.io/audio) 或开源 [MiniMax-Music3](https://huggingface.co/MiniMaxAI/MiniMax-Music3)（纯器乐 Instrumental 模式）生成后，按下方文件名保存到本目录（`apps/api/assets/music/`），再执行：",
        "",
        "```bash",
        "cd apps/api && uv run python scripts/import_library_music.py assets/music --reconcile",
        "```",
        "",
    ]
    for idx, item in enumerate(payload, start=1):
        lines.extend(
            [
                f"## {idx:02d}. {item['title_zh']} / {item['title']} (`{item['filename']}`)",
                f"- 分类：`{item['category']}` · 形态：`{item['format_kind']}`（目标 ~{item['target_duration_seconds']}s）· 风格：{item['style']} · {item['bpm']} BPM · 能量：`{item['energy']}`",
                f"- **Music 3.0 Prompt（开启纯器乐 Instrumental）**：",
                f"  > {item['prompt']}",
                "",
            ]
        )
    md_path = out_dir / "README.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Exported {len(payload)} MiniMax Music 3.0 prompts to:\n  - {json_path}\n  - {md_path}")
    return 0


async def _generate_missing(bgm_dir: Path, entries: list[CuratedMusicEntry]) -> int:
    bgm_dir.mkdir(parents=True, exist_ok=True)
    generated_count = 0
    for entry in entries:
        target = bgm_dir / entry["original_filename"]
        if target.is_file():
            print(f"  [skip] {entry['mood']}: already exists at {target}")
            continue
        print(f"  [gen ] {entry['mood']} ({USER_MODEL}, ~{entry['target_duration_seconds']}s)...")
        try:
            result = await generate_music(
                entry["generation_prompt"],
                model=USER_MODEL,
                is_instrumental=True,
                compatible_styles=entry["compatible_styles"],
                allow_synth_fallback=False,
                duration_seconds=entry["target_duration_seconds"],
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {entry['mood']}: {exc}", file=sys.stderr)
            return 2
        target.write_bytes(result.audio_bytes)
        generated_count += 1
        print(f"  [ok  ] {entry['mood']}: saved {len(result.audio_bytes)} bytes ({result.duration_seconds}s) -> {target}")
    print(f"\nGenerated {generated_count} track(s) into {bgm_dir}.")
    return 0


async def _import_one(bgm_dir: Path, entry: CuratedMusicEntry, *, overwrite: bool = False) -> bool:
    """Import one curated object. Returns True only when bytes were uploaded."""
    source = bgm_dir / entry["original_filename"]
    if not source.is_file():
        raise FileNotFoundError(f"source file is missing: {source}")
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    duration_seconds = probe_music_duration_seconds(data)

    music_id = default_music_id(entry["mood"])
    key = music_file_path(music_id)
    if await music_disk_path(music_id):
        existing = await read(key)
        if existing == data:
            print(
                f"  [skip] {entry['mood']}: identical object at {key} "
                f"(sha256={digest}, duration={duration_seconds}s)"
            )
            return False
        if not overwrite:
            raise ValueError(
                f"refusing to overwrite {key}: existing bytes do not match {source.name} (pass --overwrite to replace)"
            )

    audio = CuratedMusicAudio(
        audio_bytes=data,
        ext=AUDIO_EXT,
        duration_seconds=duration_seconds,
        size_bytes=len(data),
        content_sha256=digest,
    )
    file_path, size = await persist_music(music_id, audio)
    print(
        f"  [ok  ] {entry['mood']}: {source.name} -> {file_path} "
        f"(id={music_id}, bytes={size}, duration={duration_seconds}s, sha256={digest})"
    )
    return True


async def _main(
    bgm_dir: Path,
    moods: list[str] | None = None,
    *,
    strict: bool = False,
    overwrite: bool = False,
    reconcile: bool = False,
    generate: bool = False,
) -> int:
    entries = CURATED_MUSIC_CATALOG if moods is None else [
        entry for entry in CURATED_MUSIC_CATALOG if entry["mood"] in moods
    ]
    if generate:
        rc = await _generate_missing(bgm_dir, entries)
        if rc != 0:
            return rc

    if not bgm_dir.is_dir():
        print(f"Source BGM directory does not exist: {bgm_dir}", file=sys.stderr)
        return 1

    written = 0
    missing = 0
    for entry in entries:
        try:
            if await _import_one(bgm_dir, entry, overwrite=overwrite):
                written += 1
        except FileNotFoundError as e:
            if strict or moods is not None:
                print(f"  [FAIL] {entry['mood']}: {e}", file=sys.stderr)
                return 2
            missing += 1
            print(f"  [miss] {entry['mood']}: awaiting {entry['original_filename']}")
        except Exception as e:  # noqa: BLE001 — stop before importing later pieces
            print(f"  [FAIL] {entry['mood']}: {e}", file=sys.stderr)
            return 2

    if reconcile:
        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            created = await seed_default_music(db)
            print(f"Reconciled DB: {len(created)} new curated Music row(s) created.")

    print(
        f"\nDone. {written} object(s) written, {missing} awaiting audio; "
        "run the API (or pass --reconcile) to sync Music rows."
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import, reconcile, or export prompts for the curated MiniMax Music 3.0 library."
    )
    parser.add_argument(
        "bgm_dir",
        type=Path,
        help="Directory containing rendered <mood>.mp3 files (or target directory for --export-prompts).",
    )
    parser.add_argument(
        "--mood",
        nargs="+",
        choices=[entry["mood"] for entry in CURATED_MUSIC_CATALOG],
        help="Import only these catalog moods. Defaults to all 16 Music 3.0 catalog tracks.",
    )
    parser.add_argument(
        "--export-prompts",
        action="store_true",
        help="Write music3_prompts.json and README.md into bgm_dir and exit.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate missing tracks via MiniMax Music 3.0 API before importing.",
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Run seed_default_music against DATABASE_URL after importing.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any selected catalog MP3 is missing.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing object when local bytes differ.",
    )
    args = parser.parse_args()
    if args.export_prompts:
        raise SystemExit(_export_prompts(args.bgm_dir))
    raise SystemExit(
        asyncio.run(
            _main(
                args.bgm_dir,
                args.mood,
                strict=args.strict,
                overwrite=args.overwrite,
                reconcile=args.reconcile,
                generate=args.generate,
            )
        )
    )


if __name__ == "__main__":
    main()
