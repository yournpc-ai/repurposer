#!/bin/bash
set -eu
export LAB="${LAB:?Set LAB to an isolated experiment directory}" TMPDIR="$LAB/tmp" RENDER_PORT=49873
cd "$LAB/repo/apps/render"
export NODE_PATH=$(echo "$LAB"/repo/node_modules/.pnpm/@remotion+compositor-darwin-arm64@*/node_modules)
export NODE_OPTIONS="--require=$LAB/observe.cjs"
exec ./node_modules/.bin/tsx drive.ts "$@"
