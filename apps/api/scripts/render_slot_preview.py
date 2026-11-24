#!/usr/bin/env python3
"""Render a 1080p numbered Slot Promo MP4 (+ optional act stills) from a SkillBlueprintV1.

Usage:
  cd apps/api
  uv run python scripts/render_slot_preview.py \
    --blueprint /tmp/sample_blueprint.json \
    --style vox_editorial --locale zh \
    --out /tmp/out.mp4 --stills-dir /tmp/stills

Works completely offline/standalone without requiring the API or render HTTP
server to be running: synthesizes real 48 kHz v2 SFX WAVs via local
`@repurposer/sound-engine`, generates Pillow wireframe placeholders with pinned
NotoSansSC fonts, serves all static files over a short-lived loopback HTTP
server, and invokes Remotion headless Chrome to encode H.264 MP4 + stills.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent.parent
RENDER_DIR = REPO_ROOT / "apps" / "render"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.editing.catalog import build_sound_spec, sound_spec_digest  # noqa: E402
from app.editing.styles import StylePresetId  # noqa: E402
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks  # noqa: E402
from app.skills.blueprint import SkillBlueprintV1, load_blueprint_from_skill_version  # noqa: E402
from app.skills.slot_preview import (  # noqa: E402
    ALLOWED_FONT_FILENAMES,
    FONTS_DIR,
    build_slot_preview_video_spec,
    format_slot_checklist,
)

_SFX_NODE_SCRIPT = r"""
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { synthesizeWav } from "@repurposer/sound-engine";

const reqPath = process.argv[1];
const outDir = process.argv[2];
const cues = JSON.parse(await fs.readFile(reqPath, "utf-8"));
await fs.mkdir(outDir, { recursive: true });

const results = {};
for (const cue of cues) {
  const rendered = synthesizeWav({
    recipeId: cue.recipe_id,
    params: cue.params,
    seed: cue.seed,
  });
  const buf = Buffer.from(rendered.wav);
  const digest = createHash("sha256").update(buf).digest("hex");
  const filename = `${cue.spec_hash}.wav`;
  const dest = path.join(outDir, filename);
  await fs.writeFile(dest, buf);
  results[cue.spec_hash] = {
    filename,
    digest,
    duration_ms: rendered.acoustics.duration_ms,
  };
}
process.stdout.write(JSON.stringify(results));
"""

_RENDER_NODE_SCRIPT = r"""
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { videoSpecSchema } from "@repurposer/video-spec";
import { encodeBaselineMp4, normalizeLoudness } from "./src/audio.ts";
import { assertVideoSupported } from "./src/video/capabilities.ts";

const specPath = process.argv[1];
const outMp4 = process.argv[2];
const stillsJsonPath = process.argv[3] || "";

const raw = JSON.parse(await fs.readFile(specPath, "utf-8"));
const spec = videoSpecSchema.parse(raw);
assertVideoSupported(spec);

const entryPoint = path.resolve(process.cwd(), "src/video/remotion/entry.tsx");
const serveUrl = await bundle({ entryPoint });
const inputProps = { spec };
const composition = await selectComposition({ serveUrl, id: "Video", inputProps });

const hasSound = spec.tracks.some((track) =>
  track.clips.some(({ object }) =>
    object.kind === "audio" || (object.kind === "video" && !object.muted),
  ),
);

await fs.mkdir(path.dirname(outMp4), { recursive: true });
const workDir = await fs.mkdtemp(path.join(path.dirname(outMp4), ".slot-render-"));
const intermediate = path.join(workDir, "mix.mov");
const baseline = path.join(workDir, "baseline.mp4");

try {
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    ...(hasSound ? { audioCodec: "pcm-16" } : { muted: true }),
    ffmpegOverride: ({ type, args }) =>
      type === "pre-stitcher" && hasSound
        ? [...args.slice(0, -1), "-f", "mp4", args[args.length - 1]]
        : args,
    outputLocation: hasSound ? intermediate : baseline,
    inputProps,
    timeoutInMilliseconds: 240_000,
  });

  if (hasSound) {
    await encodeBaselineMp4(intermediate, baseline);
    await fs.unlink(intermediate);
  }

  try {
    const expectedSamples = Math.round((composition.durationInFrames * 48000) / composition.fps);
    await normalizeLoudness(baseline, expectedSamples, { requireAudio: hasSound });
  } catch (err) {
    console.error("[render_slot_preview] loudnorm skipped, keeping encoded audio:", err);
  }

  await fs.copyFile(baseline, outMp4);

  if (stillsJsonPath) {
    const stills = JSON.parse(await fs.readFile(stillsJsonPath, "utf-8"));
    for (const item of stills) {
      await fs.mkdir(path.dirname(item.output), { recursive: true });
      await renderStill({
        composition,
        serveUrl,
        frame: item.frame,
        output: item.output,
        imageFormat: "png",
        inputProps,
      });
    }
  }
} finally {
  await fs.rm(workDir, { recursive: true, force: true });
}
"""


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _start_static_server(root_dir: Path) -> tuple[_ThreadingServer, str]:
    def handler(*args: Any, **kwargs: Any) -> _QuietHandler:
        return _QuietHandler(*args, directory=str(root_dir), **kwargs)

    server = _ThreadingServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


def _synthesize_local_sfx(
    bp: SkillBlueprintV1,
    *,
    sfx_dir: Path,
    base_url: str,
) -> dict[str, tuple[UUID, str, int, str]]:
    if not bp.sfx_cues:
        return {}
    unique: dict[str, dict[str, Any]] = {}
    cue_to_hash: dict[str, str] = {}
    for cue in bp.sfx_cues:
        spec = build_sound_spec(cue.recipe_id, params=cue.params, seed=cue.seed)
        h = sound_spec_digest(spec)
        cue_to_hash[cue.cue_id] = h
        if h not in unique:
            unique[h] = {
                "spec_hash": h,
                "recipe_id": spec["recipe_id"],
                "params": spec["params"],
                "seed": spec["seed"],
            }

    req_file = sfx_dir / "_sfx_requests.json"
    req_file.write_text(json.dumps(list(unique.values())), encoding="utf-8")
    proc = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--import",
            "tsx",
            "-e",
            _SFX_NODE_SCRIPT,
            "--",
            str(req_file),
            str(sfx_dir),
        ],
        cwd=str(RENDER_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Local SFX synthesis failed:\n{proc.stderr or proc.stdout}")
    rendered = json.loads(proc.stdout)

    out: dict[str, tuple[UUID, str, int, str]] = {}
    for cue in bp.sfx_cues:
        h = cue_to_hash[cue.cue_id]
        info = rendered[h]
        digest = info["digest"]
        dur_ms = float(info["duration_ms"])
        dur_ticks = max(1, seconds_to_ticks(dur_ms / 1000.0, SOURCE_TIMEBASE))
        snap_id = uuid5(NAMESPACE_URL, f"slot-cli-sfx:{h}:{digest}")
        url = f"{base_url}/sfx/{info['filename']}"
        out[cue.cue_id] = (snap_id, digest, dur_ticks, url)
    return out


async def _load_blueprint_from_db(skill_version_id: UUID) -> tuple[str, SkillBlueprintV1]:
    from app.models.database import AsyncSessionLocal
    from app.models.tables import SkillVersion, UserSkill

    async with AsyncSessionLocal() as db:
        ver = await db.get(SkillVersion, skill_version_id)
        if ver is None:
            raise ValueError(f"SkillVersion {skill_version_id} not found in database.")
        skill = await db.get(UserSkill, ver.skill_id)
        bp = load_blueprint_from_skill_version(ver)
        return (skill.name if skill is not None else str(skill_version_id)), bp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a numbered [01]..[N] Slot Promo MP4 from a SkillBlueprintV1."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--blueprint", type=Path, help="Path to SkillBlueprintV1 JSON file.")
    source.add_argument("--skill-version-id", type=str, help="UUID of SkillVersion in DB.")
    parser.add_argument(
        "--style",
        choices=["institutional_dark", "swiss_paper", "vox_editorial", "kinetic_anime"],
        default=None,
        help="Optional CompositionStyle preset override.",
    )
    parser.add_argument("--accent", type=str, default=None, help="Optional #RRGGBB accent color.")
    parser.add_argument("--locale", choices=["zh", "en"], default="zh", help="Slot copy locale.")
    parser.add_argument("--out", type=Path, required=True, help="Output 1080p MP4 path.")
    parser.add_argument("--stills-dir", type=Path, default=None, help="Optional dir for per-act PNG stills.")
    parser.add_argument("--no-sfx", action="store_true", help="Disable v2 SFX synthesis.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.blueprint is not None:
        raw_text = args.blueprint.read_text(encoding="utf-8")
        bp = SkillBlueprintV1.model_validate_json(raw_text)
        template_name = args.blueprint.stem
        skill_version_id = uuid5(NAMESPACE_URL, f"blueprint-file:{hashlib.sha256(raw_text.encode()).hexdigest()}")
    else:
        skill_version_id = UUID(args.skill_version_id)
        template_name, bp = asyncio.run(_load_blueprint_from_db(skill_version_id))

    style_preset: StylePresetId | None = args.style
    locale: Literal["zh", "en"] = args.locale
    out_mp4 = args.out.resolve()

    with tempfile.TemporaryDirectory(prefix="slot-preview-cli-") as tmp_str:
        tmp_dir = Path(tmp_str)
        fonts_dir = tmp_dir / "fonts"
        placeholders_dir = tmp_dir / "placeholders"
        sfx_dir = tmp_dir / "sfx"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        placeholders_dir.mkdir(parents=True, exist_ok=True)
        sfx_dir.mkdir(parents=True, exist_ok=True)

        # Stage only the 4 pinned fonts into the ephemeral HTTP root
        for fname in ALLOWED_FONT_FILENAMES:
            src = FONTS_DIR / fname
            if src.is_file():
                os.symlink(src, fonts_dir / fname)

        server, base_url = _start_static_server(tmp_dir)
        try:
            sfx_snapshots = None
            if not args.no_sfx and bp.sfx_cues:
                sfx_snapshots = _synthesize_local_sfx(bp, sfx_dir=sfx_dir, base_url=base_url)

            # First pass compiles assets so we can write PNG files into placeholders_dir
            _, _, assets, _ = build_slot_preview_video_spec(
                bp,
                skill_version_id=skill_version_id,
                style_preset=style_preset,
                accent_color=args.accent,
                locale=locale,
                font_url_prefix=f"{base_url}/fonts",
                inline_placeholders=True,
                sfx_snapshots=sfx_snapshots,
            )
            placeholder_url_map: dict[UUID, str] = {}
            for asset in assets:
                fname = f"{asset.digest[:16]}.png"
                (placeholders_dir / fname).write_bytes(asset.png_bytes)
                placeholder_url_map[asset.snapshot_id] = f"{base_url}/placeholders/{fname}"

            spec, slots, _, duration_s = build_slot_preview_video_spec(
                bp,
                skill_version_id=skill_version_id,
                style_preset=style_preset,
                accent_color=args.accent,
                locale=locale,
                font_url_prefix=f"{base_url}/fonts",
                inline_placeholders=False,
                placeholder_url_map=placeholder_url_map,
                sfx_snapshots=sfx_snapshots,
            )

            spec_path = tmp_dir / "video_spec.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

            stills_arg = ""
            if args.stills_dir is not None:
                stills_dir = args.stills_dir.resolve()
                stills_dir.mkdir(parents=True, exist_ok=True)
                main_track = next(t for t in spec["tracks"] if t["track_id"] == "trk_slot_main")
                stills_plan = []
                for idx, clip in enumerate(main_track["clips"]):
                    # Pick 65% into each act so reveals & animations are settled cleanly
                    span = max(1, clip["end_frame"] - clip["start_frame"])
                    frame = min(spec["duration_frames"] - 1, clip["start_frame"] + int(span * 0.65))
                    block_id = clip["object"]["block_id"]
                    stills_plan.append({
                        "frame": frame,
                        "output": str(stills_dir / f"act_{idx + 1:02d}_{block_id}_f{frame:04d}.png"),
                    })
                stills_json = tmp_dir / "stills.json"
                stills_json.write_text(json.dumps(stills_plan), encoding="utf-8")
                stills_arg = str(stills_json)

            cmd = [
                "node",
                "--input-type=module",
                "--import",
                "tsx",
                "-e",
                _RENDER_NODE_SCRIPT,
                "--",
                str(spec_path),
                str(out_mp4),
            ]
            if stills_arg:
                cmd.append(stills_arg)

            proc = subprocess.run(
                cmd,
                cwd=str(RENDER_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                sys.stderr.write(f"Remotion render failed (exit {proc.returncode}):\n")
                sys.stderr.write(proc.stderr or proc.stdout)
                return proc.returncode
        finally:
            server.shutdown()
            server.server_close()

    checklist = format_slot_checklist(slots, locale=locale, template_name=template_name)
    print(f"Rendered: {out_mp4} ({duration_s}s, {len(bp.acts)} acts, {len(slots)} slots)")
    if args.stills_dir is not None:
        print(f"Stills dir: {args.stills_dir.resolve()}")
    print()
    print(checklist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
