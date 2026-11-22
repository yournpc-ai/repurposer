#!/bin/bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
work=$(bash "$here/setup.sh")
echo "Isolated run: $work"
cd "$work"
source env.sh
"$PY" src/run-b.py
"$PY" -c 'import sys;sys.path.insert(0,"src");from bench import measure;sys.exit(measure([sys.executable,"src/c.py"],"C"))'
"$PY" src/controlled.py
"$PY" src/preview.py
"$PY" src/analyze.py
"$PY" src/source_ids.py
"$PY" src/history.py "$here/../baseline"
"$PY" src/provenance.py
echo "Evidence: $work/evidence"
