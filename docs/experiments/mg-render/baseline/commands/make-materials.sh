#!/bin/bash
set -euo pipefail
# Run only in a fresh isolated run as these commands create fixture inputs.
source "$(cd "$(dirname "$0")/.." && pwd)/env.sh"
cd "$LAB"
say -v Samantha -r 174 -o assets/narration.aiff 'Two clocks, one cut. Watch the signals meet, then follow the second pulse.'
afconvert -f WAVE -d LEI16@48000 assets/narration.aiff assets/voice.wav
"$PY" src/materials.py
