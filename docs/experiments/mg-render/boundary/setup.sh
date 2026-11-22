#!/bin/bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(git -C "$here" rev-parse --show-toplevel)
work=$(mktemp -d /tmp/repurposer-boundary.XXXXXX)
cp -R "$here/src" "$here/../baseline/"{assets,fixture} "$work/"
cp "$here/../baseline/"{package.json,package-lock.json} "$work/"
cd "$work"
mkdir -p cache evidence logs
if [[ -n "${ABC_MODULES:-}" ]]; then ln -s "$ABC_MODULES" node_modules; else npm ci >&2; fi
cp "$here/../baseline/src/"{audio_oracle,bench,seek_server}.py src/
cp "$repo/packages/video-remotion/src/Video.tsx" src/Video.tsx
sed -i '' 's|"@repurposer/video-spec"|"./video-spec"|' src/Video.tsx
cp -R "$repo/packages/video-spec/src" src/video-spec
cat > env.sh <<ENV
export REP="$repo"
export PY="$repo/apps/api/.venv/bin/python"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$repo/apps/api"
export FFBIN="$repo/node_modules/.pnpm/@remotion+compositor-darwin-arm64@4.0.484/node_modules/@remotion/compositor-darwin-arm64"
export CHROME="$repo/apps/render/node_modules/.remotion/chrome-headless-shell/mac-arm64/chrome-headless-shell-mac-arm64/chrome-headless-shell"
ENV
source env.sh
shasum -a 256 -c fixture/font.sha256 >&2
"$PY" src/prepare.py
echo "$work"
