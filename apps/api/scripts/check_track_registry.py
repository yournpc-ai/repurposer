#!/usr/bin/env python3
"""Double-end drift guard for TRACK_REGISTRY (ADR-044).

Diffs the TS catalog (``packages/clip/src/tracks.ts`` — the source of truth)
against the Python mirror (``app/pipeline/tracks.py``). Any drift fails loud
with both sides printed.

    cd apps/api && uv run python scripts/check_track_registry.py
"""

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parents[3]


def ts_catalog() -> dict:
    # tsx lives in apps/render (no package at the workspace root); import the
    # catalog by absolute path from there.
    proc = subprocess.run(
        [
            "pnpm", "exec", "tsx", "-e",
            f"import {{ TRACK_REGISTRY }} from '{REPO_ROOT}/packages/clip/src/tracks';"
            " console.log(JSON.stringify(TRACK_REGISTRY))",
        ],
        cwd=REPO_ROOT / "apps" / "render",
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print("TS catalog dump failed (need pnpm + tsx on PATH):\n" + proc.stderr)
        sys.exit(2)
    # tsx may print preamble lines; the catalog is the last JSON line
    for line in reversed(proc.stdout.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    print("TS catalog dump produced no JSON:\n" + proc.stdout)
    sys.exit(2)


def main() -> int:
    from app.pipeline.tracks import TRACKS

    ts = ts_catalog()
    py = {name: asdict(track) for name, track in TRACKS.items()}
    # tuples -> lists for JSON comparison
    py = json.loads(json.dumps(py))

    ok = True
    for name in sorted(set(ts) | set(py)):
        if name not in ts:
            print(f"✘ track '{name}': only in Python mirror")
            ok = False
            continue
        if name not in py:
            print(f"✘ track '{name}': only in TS catalog")
            ok = False
            continue
        a, b = ts[name], py[name]
        if a != b:
            ok = False
            print(f"✘ track '{name}' drifts:")
            for key in sorted(set(a) | set(b)):
                if a.get(key) != b.get(key):
                    print(f"    {key}: TS={a.get(key)!r}  PY={b.get(key)!r}")
    if ok:
        print(f"✔ TRACK_REGISTRY double-end in sync ({len(ts)} tracks)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
