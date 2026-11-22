#!/bin/bash
# Execute from any directory on an arm64 Mac with the locked Chromium already available.
set -eu -o pipefail
archive=$(cd "$(dirname "$0")/.." && pwd)
research=$(dirname "$archive")
repo=$(git -C "$archive" rev-parse --show-toplevel)
python=${MEASURE_PYTHON:-$repo/apps/api/.venv/bin/python}
lab=$(mktemp -d "${TMPDIR:-/tmp}/i8-sample-backport.XXXXXX")
work=$lab/clean
run=$lab/mac
mkdir -p "$work" "$run/assets" "$run/tmp" "$lab/skips/tmp" "$lab/skips/run/"{silent,absent}
echo "Isolated workspace: $lab"
git -C "$repo" archive 0d16d514c80cefd4d5273bba1bcd3abb407a800a apps/render apps/web/package.json packages pnpm-lock.yaml pnpm-workspace.yaml | tar -x -C "$work"
cd "$work"
patch -p1 < "$research/joint-candidate/candidate.diff"
patch -p1 < "$archive/evidence/mux-command.diff"
patch -p1 < "$archive/evidence/lock.diff"
cp -R "$archive/patches" .
cat >> pnpm-workspace.yaml <<'YAML'

patchedDependencies:
  '@remotion/renderer@4.0.484': patches/@remotion__renderer@4.0.484.patch
YAML
pnpm --filter @repurposer/render... install --frozen-lockfile --store-dir "$lab/store"
"$python" "$archive/tools/verify_install.py" "$repo/apps/render/node_modules/@remotion/renderer" "$work/apps/render/node_modules/@remotion/renderer"
cp -cR "$repo/apps/render/node_modules/.remotion" "$work/apps/render/node_modules/.remotion"
cp "$repo/docs/experiments/mg-render/baseline/assets/"{main.mp4,voice.wav,whoosh.wav,impact2.wav} "$run/assets/"
cp "$research/joint-candidate/boundary/boundary.json" "$run/boundary.json"
cp "$research/clock-boundaries/audio/spec.json" "$run/edge.json"
cp "$research/clock-boundaries/regression/mix.json" "$run/mix.json"
cp "$research/joint-candidate/tools/"{drive.mts,observe-boundary.cjs} "$run/"
cd "$work/apps/render"
export RENDER_PORT=49873
export NODE_OPTIONS="--require=$run/observe-boundary.cjs"
for mode in boundary edge success encodeFail; do
    LAB="$run" TMPDIR="$run/tmp" ./node_modules/.bin/tsx "$run/drive.mts" "$mode"
done
./node_modules/.bin/tsc --noEmit
native="$work/node_modules/.pnpm/@remotion+compositor-darwin-arm64@4.0.484/node_modules/@remotion/compositor-darwin-arm64"
DYLD_LIBRARY_PATH="$native" "$native/ffmpeg" -v error -i "$run/run/success/raw.mp4" -map 0:v:0 -an -c:v copy "$lab/skips/run/absent/probe.mp4"
DYLD_LIBRARY_PATH="$native" "$native/ffmpeg" -v error -i "$run/run/success/raw.mp4" -af volume=0 -c:v copy -c:a libfdk_aac -b:a 320k -movie_timescale 48000 "$lab/skips/run/silent/probe.mp4"
cp "$archive/tools/skip.mts" "$lab/skips/"
LAB="$lab/skips" TMPDIR="$lab/skips/tmp" ./node_modules/.bin/tsx "$lab/skips/skip.mts" > "$lab/skip-results.jsonl"
"$python" "$archive/tools/mux_control.py" "$run/commands.jsonl" "$run/run/boundary/raw.mp4" "$lab/mux-1000.mp4" "$lab/control.json"
"$python" "$research/joint-candidate/tools/collect.py" "$run" "$research/clock-boundaries/measure.py" "$lab/mac.json"
CURRENT_METRICS="$lab/mac.json" "$python" -B "$archive/tools/check_clocks.py" "$lab" "$archive" > "$lab/clocks.json"
echo "Measured result: $lab/clocks.json"
