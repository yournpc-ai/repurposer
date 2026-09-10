#!/bin/bash
# Dev launcher: starts Postgres (if needed), the API, and the web app.
# Deliberately avoids `set -e` so one service failing doesn't kill the rest,
# and never blocks on an unresponsive Docker daemon.

echo "Starting Repurposer development environment..."

# Always run relative to the repo root, regardless of where this is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "Cannot cd to repo root ($ROOT)"; exit 1; }

export DEMO_SEED_ASYNC=true

# --- helpers ---------------------------------------------------------------
kill_port() {
  local port=$1 name=$2 pids
  pids=$(lsof -ti :"$port" 2>/dev/null)
  if [ -n "$pids" ]; then
    echo "Killing existing $name on port $port..."
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null
  fi
}

# Run a command with a timeout, even without coreutils' `timeout`.
with_timeout() {
  local secs=$1; shift
  "$@" &
  local cmd_pid=$!
  ( sleep "$secs"; kill -9 "$cmd_pid" 2>/dev/null ) &
  local killer=$!
  if wait "$cmd_pid" 2>/dev/null; then
    kill "$killer" 2>/dev/null
    return 0
  fi
  return 1
}

port_in_use() { lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# Wait until a URL returns HTTP 200, up to a timeout.
wait_for_url() {
  local url=$1 name=$2 timeout=${3:-30}
  echo "Waiting for $name to be ready..."
  for ((i=0; i<timeout; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready."
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $name (continuing anyway)."
  return 1
}

# --- kill previous service instances -----------------------------------------
# 2026-09-11 用户拍板：dev.sh 启动 = 干净 slate——全机每个服务只剩本次启动
# 的一个实例（一对：包装器 + 本体）。端口杀（kill_port）只拿到监听者本人：
# 包装器（uv run / pnpm / npm exec）与 watcher 父进程（tsx watch——它还会把
# 被杀的子进程原地复活）全部漏网（当日实测：render 躺着一对上次的孤儿
# watcher、web 躺着一个没抢到端口的旧 vite）；uvicorn --reload 的 spawn 子
# 进程反过来不带识别字符串。所以两趟模式杀（TERM → KILL）在前、端口杀殿后
# ——端口杀兜的正是 spawn 子进程这类无特征监听者。
# 注意：模式杀认 argv 特征串，与仓库外同命令行的进程（别的 tsx watch
# src/server.ts 项目）会误伤——本机开发约定下可接受。
SERVICE_PATTERNS=(
  "uvicorn app\.main"        # API：uv run 包装器 + reload 主进程
  "\-m app\.worker"          # worker：无端口，只能模式杀（2026-09-08 孤儿教训）
  "src/server\.ts"           # render：tsx watch 父与 node 子 argv 同串
  "vite/bin/vite\.js dev"    # web：vite 本体（pnpm 包装器随子进程退出）
)

kill_service_families() {
  local signal=$1 pattern pids
  for pattern in "${SERVICE_PATTERNS[@]}"; do
    pids=$(pgrep -f "$pattern" 2>/dev/null)
    if [ -n "$pids" ]; then
      echo "Killing $pattern: $(echo $pids | tr '\n' ' ')"
      # shellcheck disable=SC2086
      kill "$signal" $pids 2>/dev/null
    fi
  done
}

kill_service_families -TERM
sleep 2
# TERM 幸存者 + tsx watch 复活竞态，一律 KILL 收尾。
kill_service_families -9

# 端口杀殿后（uvicorn reload 的 spawn 子进程只有端口认得它）。
kill_port 8000 "backend"
kill_port 3000 "frontend"
kill_port 3001 "render"

# --- PostgreSQL ------------------------------------------------------------
if port_in_use 5432; then
  echo "PostgreSQL already running on 5432, skipping Docker."
elif with_timeout 5 docker ps >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q repurposer-db; then
    echo "Starting PostgreSQL (Docker)..."
    docker run -d --name repurposer-db \
      -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres \
      -e POSTGRES_DB=repurposer \
      -p 5432:5432 \
      postgres:18-alpine 2>/dev/null \
      || docker start repurposer-db 2>/dev/null \
      || echo "Could not start Postgres container (continuing anyway)."
  fi
else
  echo "Docker is unavailable or unresponsive — skipping Postgres startup."
  echo "  (Make sure Postgres is reachable on 5432 yourself.)"
fi

# --- database migrations ---------------------------------------------------
# Apply Alembic migrations before starting the API so schema issues surface
# immediately rather than inside the FastAPI lifespan.
if port_in_use 5432 || with_timeout 5 docker ps >/dev/null 2>&1; then
  echo "Applying database migrations..."
  ( cd "$ROOT/apps/api" && uv run alembic upgrade head ) || echo "Migration step exited (continuing anyway)."
else
  echo "Postgres does not appear to be available — skipping migrations."
fi

# --- backend ---------------------------------------------------------------
echo "Starting API on http://localhost:8000 ..."
( cd "$ROOT/apps/api" && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 ) &
API_PID=$!

# --- worker ----------------------------------------------------------------
# Processes the Postgres-backed job queue (asset processing + generation) in a
# separate process so heavy jobs don't compete with the API's online requests.
echo "Starting background worker ..."
( cd "$ROOT/apps/api" && uv run python -m app.worker ) &
WORKER_PID=$!

# Wait for the API to finish startup before launching the frontend, otherwise
# the first page fetch races the FastAPI application lifespan.
wait_for_url "http://localhost:8000/health" "API" 60

# --- render service --------------------------------------------------------
# Remotion render service (clip-spec -> MP4+SRT). Node/pnpm, headless Chrome +
# bundled FFmpeg. Black box the api worker calls; not needed for text-only flows.
#
# Proxy: the direct link from a dev machine to TOS is throttled, and the
# service's source staging + result upload are proxy-aware via HTTPS_PROXY
# (loopback exempt). When the local proxy is listening, carry the env into
# the render service so large-media transfers don't die on undici timeouts
# (2026-08-19: a hand restart without the env reproduced exactly that — the
# render SUCCEEDS and only the PUT upload times out).
echo "Starting render service on http://localhost:3001 ..."
if nc -z 127.0.0.1 6152 2>/dev/null; then
  ( cd "$ROOT/apps/render" && HTTPS_PROXY="http://127.0.0.1:6152" HTTP_PROXY="http://127.0.0.1:6152" pnpm dev ) &
else
  ( cd "$ROOT/apps/render" && pnpm dev ) &
fi
RENDER_PID=$!

# --- frontend --------------------------------------------------------------
echo "Starting web app on http://localhost:3000 ..."
( cd "$ROOT/apps/web" && pnpm dev ) &
WEB_PID=$!

# --- startup liveness gate ---------------------------------------------------
# 2026-09-06 lesson: the worker died seconds after launch (an unguarded
# startup exception) and nothing said so — its traceback scrolled by under
# the other services' logs and a user's run queued forever. The API has
# wait_for_url; the other three had NOTHING. Give every service a few
# seconds to prove it's alive, then SAY the verdict per service.
check_alive() {
  local pid=$1 name=$2 hint=$3
  if kill -0 "$pid" 2>/dev/null; then
    echo "  ✔ $name (pid $pid)"
    return 0
  fi
  echo "  ✘ $name DIED AT STARTUP — its traceback is above."
  echo "    rerun: $hint"
  return 1
}

sleep 5
echo "Service status:"
DEAD=0
check_alive "$API_PID"    "API    http://localhost:8000"  "( cd apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 )" || DEAD=1
check_alive "$WORKER_PID" "worker (job queue)"            "( cd apps/api && uv run python -m app.worker )"                                   || DEAD=1
check_alive "$RENDER_PID" "render http://localhost:3001"  "( cd apps/render && pnpm dev )"                                                   || DEAD=1
check_alive "$WEB_PID"    "web    http://localhost:3000"  "( cd apps/web && pnpm dev )"                                                      || DEAD=1
# Unique-instance guard (2026-09-08 worker 孤儿教训，2026-09-11 推广到全家):
# 启动前已两趟模式杀，此刻每个服务家族的匹配进程都该只属于本次启动——
# 超出预期计数 = 孤儿/复活，大声说出来并列 offender。
# 预期计数：API 2（uv run 包装器 + uvicorn 主进程；reload 的 spawn 子进程
# 不带特征串，不计）、worker 2、render 2（tsx watch 父 + node 子）、web 1
# （vite 本体；pnpm 包装器 argv 无特征）。
family_count() { pgrep -f "$1" 2>/dev/null | wc -l | tr -d ' '; }
check_family() {
  local pattern=$1 name=$2 max=$3 count
  count=$(family_count "$pattern")
  if [ "$count" -gt "$max" ]; then
    echo "  ⚠ $name: $count processes match '$pattern' (expected ≤ $max) — orphans will run STALE code:"
    pgrep -fl "$pattern"
    DEAD=1
  fi
}
check_family "uvicorn app\.main"     "API   " 2
check_family "\-m app\.worker"       "worker" 2
check_family "src/server\.ts"        "render" 2
check_family "vite/bin/vite\.js dev" "web   " 1
if [ "$DEAD" -ne 0 ]; then
  echo "⚠ One or more services failed to start — the environment is NOT whole."
fi

# --- cleanup ---------------------------------------------------------------
# Ctrl+C 也要干净：先杀本次启动的四个 PID，再按家族模式清场——包装器死了
# 不保证 spawn 子进程 / watcher 跟着死，不留任何能给下次启动添乱的东西。
trap 'echo; echo "Shutting down..."; kill "$API_PID" "$WORKER_PID" "$RENDER_PID" "$WEB_PID" 2>/dev/null; sleep 1; kill_service_families -9; exit' INT TERM

wait
