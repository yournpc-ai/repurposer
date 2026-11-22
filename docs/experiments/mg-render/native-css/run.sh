#!/bin/bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
export MG=${MG:-$(dirname "$here")}
export REP=$(git -C "$MG" rev-parse --show-toplevel)
source "$MG/baseline/env.sh"
work=$(mktemp -d /tmp/mg-css-run.XXXXXX)
cd "$work"
echo "Run directory $work"
cp -R "$here/src" .
cp "$MG/baseline/"{package.json,package-lock.json} .
ln -s "$MG/baseline/assets" assets
cp "$MG/baseline/src/"{bench,verify,audio_oracle}.py src/
mkdir cache logs evidence
if [[ -n "${ABC_MODULES:-}" ]]; then ln -s "$ABC_MODULES" node_modules; else npm ci; fi
shasum -a 256 -c "$MG/baseline/fixture/font.sha256"
"$PY" src/prepare.py
"$PY" src/run.py
"$PY" src/analyze.py
