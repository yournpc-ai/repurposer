"""crop_track dual-end parity fixture (ADR-045 D5): the TS sampler
(``packages/clip/src/types.ts sampleCrop``) and the Python twin
(``clip_spec.sample_crop``) must agree EXACTLY at every sampled source
second — keyframe instants, ease-window interiors, before-the-first and
after-the-last holds, and the empty-track static-crop degenerate.

    cd apps/api && uv run python scripts/crop_track_parity.py
"""

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import ClipSpec  # noqa: E402
from app.pipeline.clip_spec import sample_crop  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TSX = REPO / "node_modules/.pnpm/tsx@4.22.4/node_modules/tsx/dist/cli.mjs"
HARNESS = REPO / "packages/clip/scripts/crop_track_parity.ts"

BASE_SPEC = {
    "source": {"asset_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "url": "k", "fps": 30},
    "aspect": "9:16",
    "segments": [{"id": "a", "start": 0.0, "end": 30.0, "hidden": False, "transition": "none"}],
    "crop": {"x": 0.5, "y": 0.5, "scale": 1.0},
    "crop_track": [
        {"t": 2.0, "x": 0.25, "y": 0.4, "scale": 2.0},
        {"t": 10.0, "x": 0.75, "y": 0.45, "scale": 1.8},
        {"t": 20.0, "x": 0.5, "y": 0.5, "scale": 1.5},
    ],
    "caption_track": [],
    "caption_style_preset": "clean-bottom",
    "layers": [],
    "title": {"text": "", "enabled": False},
    "music": {"enabled": False, "gain_db": -18},
    "brand_ref": None,
    "target_language": "en",
}

# Dense sweep + the exact keyframe instants, ease-window edges (k.t + 8/30),
# pre-first hold and post-last hold.
TIMES = sorted(
    {0.0, 1.0, 2.0, 10.0, 20.0, 30.0, 2.0 + 8 / 30, 10.0 + 8 / 30, 20.0 + 8 / 30}
    | {t / 20 for t in range(0, 601)}
)


def main() -> None:
    spec = ClipSpec.model_validate(BASE_SPEC).model_dump(mode="json")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"spec": spec, "times": TIMES}, f)
        tmp = f.name

    for label, spec_obj in [("track", spec), ("empty-track", {**spec, "crop_track": []})]:
        if label == "empty-track":
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump({"spec": spec_obj, "times": TIMES}, f)
                tmp = f.name
        ts_out = json.loads(
            subprocess.run(
                ["node", str(TSX), str(HARNESS), tmp],
                check=True, capture_output=True, text=True,
            ).stdout
        )
        py_out = [sample_crop(spec_obj, t) for t in TIMES]
        mismatches = [
            (t, ts, py)
            for t, ts, py in zip(TIMES, ts_out, py_out)
            if any(not math.isclose(ts[k], py[k], rel_tol=0, abs_tol=0) for k in ("x", "y", "scale"))
        ]
        if mismatches:
            for t, ts, py in mismatches[:5]:
                print(f"MISMATCH @{label} t={t}: ts={ts} py={py}")
            sys.exit(f"parity FAILED at {label}: {len(mismatches)}/{len(TIMES)}")
        print(f"parity OK [{label}]: {len(TIMES)} samples, exact equality")

    # Empty track must equal the static crop pixel-for-pixel (degenerate form).
    static = BASE_SPEC["crop"]
    py_static = sample_crop({**spec, "crop_track": []}, 7.7)
    assert py_static == static, (py_static, static)
    print("degenerate OK: empty track == static crop")

    # Contract: unsorted keyframes are rejected at validation.
    bad = json.loads(json.dumps(BASE_SPEC))
    bad["crop_track"] = [bad["crop_track"][1], bad["crop_track"][0]]
    try:
        ClipSpec.model_validate(bad)
        sys.exit("validator FAILED: unsorted crop_track accepted")
    except Exception:
        print("validator OK: unsorted crop_track rejected")


if __name__ == "__main__":
    main()
