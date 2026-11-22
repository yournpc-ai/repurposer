#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/env.sh"
base="$LAB"
dest=$(mktemp -d /tmp/repurposer-abc-repeat.XXXXXX)
echo "New isolated experiment: $dest"
cd "$dest"
cp -R "$base/src" "$base/commands" .
cp "$base"/{env.sh,package.json,package-lock.json} .
mkdir -p assets cache fixture logs analysis results
# Input media are pinned. Regeneration timings are a separate test from replay.
cp "$base"/assets/{narration.aiff,voice.wav,main.mp4,pip.mp4,whoosh.wav,impact1.wav,impact2.wav} assets/
cp "$base"/fixture/{recipes.json,font.sha256} fixture/
if [[ -n "${ABC_MODULES:-}" ]]; then ln -s "$ABC_MODULES" node_modules; else npm ci; fi
source ./env.sh
export COMPONENT_BAKE_ENABLED=true
"$PY" src/fixture.py
"$PY" src/bench.py ABC
"$PY" src/conform.py
"$PY" src/preview.py
"$PY" src/verify.py
"$PY" src/recovery.py
"$PY" src/encoder_control.py
"$PY" src/local_audio_edit.py
"$PY" src/material_cost.py
"$PY" src/summarize.py
