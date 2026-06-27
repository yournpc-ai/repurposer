# Remotion render service (clip-spec -> MP4 + SRT). Node + pnpm workspace.
#
# Build context is the REPO ROOT (not apps/render): this package imports the
# workspace package @repurposer/clip, so the build needs pnpm-workspace.yaml,
# the lockfile, and packages/clip — none of which live under apps/render.
FROM node:22-bookworm-slim

# @remotion/renderer ships its own Chromium binary but launches it through
# these system shared libs (headless Chrome runtime deps + base fonts).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libxshmfence1 libasound2 libpango-1.0-0 \
        libcairo2 libatspi2.0-0 fonts-liberation fonts-noto-color-emoji \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin pnpm to the repo's version (matches local; lockfile is v9.0). Without a
# packageManager field, bare `corepack enable` grabs the latest pnpm (11.x),
# whose minimumReleaseAge supply-chain policy rejects freshly-published deps
# (e.g. a day-old Remotion release) even against a committed --frozen-lockfile.
RUN corepack enable && corepack prepare pnpm@10.20.0 --activate

WORKDIR /repo

# Workspace descriptors first so dependency install is a cached layer.
# Every workspace member's manifest must be present for pnpm to resolve the
# graph, even though --filter only installs the render branch.
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/clip/package.json packages/clip/package.json
COPY apps/render/package.json apps/render/package.json
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --filter @repurposer/render... --frozen-lockfile

# Source for the render branch only.
COPY packages/clip packages/clip
COPY apps/render apps/render

# NOTE: Remotion's headless Chromium (~90MB) is fetched lazily on the first
# render, not baked at build time. Build-time downloads make the image build
# depend on outbound network (and hang on constrained/CI networks); the render
# service already has network at run time (it fetches source clips over HTTP).
# To avoid re-downloading on every container restart, mount a cache volume at
# the Remotion download dir in production.

WORKDIR /repo/apps/render
ENV RENDER_PORT=3001
# Rendered MP4/SRT land here; the api serves them from the shared volume.
ENV RENDER_OUTPUT_DIR=/data/outputs
EXPOSE 3001
CMD ["pnpm", "start"]
