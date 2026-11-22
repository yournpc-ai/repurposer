#!/bin/bash
set -euo pipefail
export CLOCK=$(cd "$(dirname "$0")" && pwd)
export MG=$(cd "$CLOCK/../.." && pwd)
source "$MG/baseline/env.sh"
cd "$(mktemp -d /tmp/mg-clock.XXXXXX)"
echo "Results in $PWD/evidence"
mkdir cache logs evidence
cp -R "$CLOCK/../src" .
cp "$MG/baseline/"{package.json,package-lock.json} .
ln -s "$MG/baseline/assets" assets
export PYTHONPATH="$PYTHONPATH:$PWD/src:$MG/baseline/src"
shasum -a 256 -c "$MG/baseline/fixture/font.sha256"
if [[ -n "${ABC_MODULES:-}" ]]; then ln -s "$ABC_MODULES" node_modules; else npm ci --no-audit --no-fund; fi
"$PY" src/prepare.py
cmp evidence/v7.json "$CLOCK/../evidence/v7.json"
build() {
  node_modules/.bin/esbuild src/C.tsx --bundle '--define:process.env.NODE_ENV="production"' --outfile="cache/$1.js"
  echo "<body style='margin:0'><script src='$1.js'></script></body>" > "cache/$1.html"
}
build original
cp "$CLOCK/Readout.tsx" src/
patch -p1 < "$CLOCK/host.diff"
build clock
for phase in prepare sequence seek replay; do
  "$PY" -c 'from bench import measure; import sys,os; sys.exit(measure([sys.executable, os.environ["CLOCK"]+"/study.py",sys.argv[1]],sys.argv[1]))' "$phase" || { cat "logs/$phase.log"; exit 1; }
done
cp logs/bench.jsonl evidence/

for result in v8 v9 sequence audio seek replay uncontrolled; do
  cmp "evidence/$result.json" "$CLOCK/evidence/$result.json"
done
