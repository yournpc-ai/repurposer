#!/bin/bash
# Dev launcher: starts Postgres (if needed), the API, and the web app.
# Deliberately avoids `set -e` so one service failing doesn't kill the rest,
# and never blocks on an unresponsive Docker daemon.

echo "Starting Rookie Cut development environment..."

# Always run relative to the repo root, regardless of where this is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "Cannot cd to repo root ($ROOT)"; exit 1; }

export DEMO_SEED_ASYNC=true

# The Node render process does not load the repository .env itself. Forward
# only the component-runner opt-in; an explicit process environment wins.
if [ -z "${COMPONENT_BAKE_ENABLED+x}" ] && [ -r "$ROOT/.env" ]; then
  while IFS= read -r line; do
    case "$line" in
      COMPONENT_BAKE_ENABLED=*) export COMPONENT_BAKE_ENABLED="${line#*=}" ;;
    esac
  done < "$ROOT/.env"
fi

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

# Each long-running service has one supervisor. PID files let the next dev.sh
# stop old supervisors BEFORE their children; killing only the children would
# otherwise make an old supervisor restart them into the new stack.
SUPERVISOR_DIR="${TMPDIR:-/tmp}/repurposer-dev-supervisors"
mkdir -p "$SUPERVISOR_DIR"
stop_stale_supervisors() {
  local unit pidfile pid command
  for unit in api worker render web; do
    pidfile="$SUPERVISOR_DIR/$unit.pid"
    [ -r "$pidfile" ] || continue
    pid=$(<"$pidfile")
    command=$(ps -p "$pid" -o command= 2>/dev/null || true)
    if [ -n "$pid" ] && [[ "$command" == *"scripts/dev.sh"* ]]; then
      echo "Stopping previous $unit supervisor (pid $pid)..."
      kill -TERM "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  done
}

# A supervisor restarts only when its own service exits. TERM is an explicit
# shutdown, not a crash: the pipeline's service family is cleaned by dev.sh.
supervise() {
  local unit=$1 logfile=$2; shift 2
  (
    trap 'exit 0' TERM INT
    sh -c 'echo $PPID' > "$SUPERVISOR_DIR/$unit.pid"
    while true; do
      echo "$(date '+%Y-%m-%d %H:%M:%S') [$unit] starting" | tee -a "$logfile"
      "$@"
      status=$?
      echo "$(date '+%Y-%m-%d %H:%M:%S') [$unit] exited (status $status); restarting in 2s" | tee -a "$logfile"
      sleep 2
    done
  ) &
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
  "scripts/dev_worker\.py|\-m app\.worker"  # worker：uv、文件监视器和队列进程
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

stop_stale_supervisors
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

# --- per-service log files --------------------------------------------------
# 2026-10-16 取证教训: 终端 scrollback 不是台账——一次 37 分钟的链上失败
# (film 分镜起草穷举) 的 violation codes 随窗口关闭灭失。每个服务 tee 一份
# 到 /tmp,启动时截断一次；自动重启追加，不覆盖上一段崩溃证据。
LOG_API=/tmp/rep-api.log
LOG_WORKER=/tmp/rep-worker.log
LOG_RENDER=/tmp/rep-render.log
LOG_WEB=/tmp/rep-web.log
: > "$LOG_API"; : > "$LOG_WORKER"; : > "$LOG_RENDER"; : > "$LOG_WEB"

api_command() {
  ( cd "$ROOT/apps/api" && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 | tee -a "$LOG_API" )
}
worker_command() {
  (
    set -o pipefail
    cd "$ROOT/apps/api" && uv run python scripts/dev_worker.py 2>&1 | tee -a "$LOG_WORKER"
  )
}
web_command() {
  ( cd "$ROOT/apps/web" && pnpm dev 2>&1 | tee -a "$LOG_WEB" )
}

# --- backend ---------------------------------------------------------------
echo "Starting API on http://localhost:8000 (auto-restart enabled) ..."
supervise api "$LOG_API" api_command
API_PID=$!

# --- worker ----------------------------------------------------------------
# Processes the Postgres-backed job queue in a separate process so heavy jobs
# never compete with the API's online requests.
echo "Starting background worker (file reload and auto-restart enabled) ..."
supervise worker "$LOG_WORKER" worker_command
WORKER_PID=$!

# Wait for the API to finish startup before launching the frontend, otherwise
# the first page fetch races the FastAPI application lifespan.
wait_for_url "http://localhost:8000/health" "API" 60

# --- render service --------------------------------------------------------
# Remotion render service (clip-spec -> MP4+SRT). Node/pnpm, headless Chrome +
# bundled FFmpeg. Black box the api worker calls; not needed for text-only flows.
#
# Only render receives the proxy; API/worker keep their existing networking.
# Explicit opt-out wins over inherited variables. A transient probe failure
# must not silently switch a configured proxy to the throttled direct path.
echo "Starting render service on http://localhost:3001 (auto-restart enabled) ..."
RENDER_PROXY_ENV=()
if [ "${RENDER_PROXY:-}" = "off" ]; then
  RENDER_PROXY_ENV=(-u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy -u ALL_PROXY -u all_proxy)
  echo "  render proxy: OFF (explicit)" | tee -a "$LOG_RENDER"
else
  RENDER_PROXY_URL=${RENDER_PROXY:-${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}}
  if [ -z "$RENDER_PROXY_URL" ] && command -v scutil >/dev/null 2>&1; then
    RENDER_PROXY_URL=$(scutil --proxy | awk '
      $1 == "HTTPSEnable" { enabled=$3 }
      $1 == "HTTPSProxy" { host=$3 }
      $1 == "HTTPSPort" { port=$3 }
      END { if (enabled == 1 && host != "" && port != "") print "http://" host ":" port }
    ')
  fi
  RENDER_PROXY_URL=${RENDER_PROXY_URL:-http://127.0.0.1:6152}
  case "$RENDER_PROXY_URL" in *://*) ;; *) RENDER_PROXY_URL="http://$RENDER_PROXY_URL" ;; esac
  RENDER_PROXY_ENV=("HTTPS_PROXY=$RENDER_PROXY_URL" "HTTP_PROXY=$RENDER_PROXY_URL")
  if curl -s -o /dev/null --connect-timeout 3 --max-time 8 --noproxy '' -x "$RENDER_PROXY_URL" "https://repurposer.tos-ap-southeast-1.volces.com/"; then
    echo "  render proxy: enabled (TOS connectivity probe passed)" | tee -a "$LOG_RENDER"
  else
    echo "  render proxy: enabled but TOS probe failed; keeping proxy. Check Surge or explicitly use RENDER_PROXY=off." | tee -a "$LOG_RENDER"
  fi
fi
render_command() {
  ( cd "$ROOT/apps/render" && env "${RENDER_PROXY_ENV[@]}" pnpm dev 2>&1 | tee -a "$LOG_RENDER" )
}
supervise render "$LOG_RENDER" render_command
RENDER_PID=$!

# --- frontend --------------------------------------------------------------
echo "Starting web app on http://localhost:3000 (auto-restart enabled) ..."
supervise web "$LOG_WEB" web_command
WEB_PID=$!

# --- startup liveness gate ---------------------------------------------------
# 2026-09-06 lesson: the worker died seconds after launch (an unguarded
# startup exception) and nothing said so — its traceback scrolled by under
# the other services' logs and a user's run queued forever. The API has
# wait_for_url; the other three had NOTHING. Give every service a few
# seconds to prove it's alive, then SAY the verdict per service.
# Supervisors add a second check: a living supervisor with zero children is
# a crash loop, not a healthy service.
check_alive() {
  local pid=$1 name=$2 hint=$3
  if kill -0 "$pid" 2>/dev/null; then
    echo "  ✔ $name (supervisor pid $pid)"
    return 0
  fi
  echo "  ✘ $name SUPERVISOR DIED AT STARTUP — its traceback is above."
  echo "    rerun: $hint"
  return 1
}

sleep 5
echo "Service status:"
DEAD=0
check_alive "$API_PID"    "API    http://localhost:8000"  "( cd apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 )" || DEAD=1
check_alive "$WORKER_PID" "worker (job queue)"            "( cd apps/api && uv run python scripts/dev_worker.py )"                                   || DEAD=1
check_alive "$RENDER_PID" "render http://localhost:3001"  "( cd apps/render && HTTPS_PROXY=http://127.0.0.1:6152 pnpm dev )"                   || DEAD=1
check_alive "$WEB_PID"    "web    http://localhost:3000"  "( cd apps/web && pnpm dev )"                                                         || DEAD=1
# Unique-instance guard：启动时每个服务家族必须恰好有预期进程数；少了是
# 崩溃/重启中，多了是孤儿/复活。API 2、worker 3（含文件监视器）、render 2、web 1。
family_count() { pgrep -f "$1" 2>/dev/null | wc -l | tr -d ' '; }
check_family() {
  local pattern=$1 name=$2 expected=$3 count
  count=$(family_count "$pattern")
  if [ "$count" -ne "$expected" ]; then
    echo "  ⚠ $name: $count processes match '$pattern' (expected $expected) — service is down, restarting, or orphaned:"
    pgrep -fl "$pattern"
    DEAD=1
  fi
}
check_family "uvicorn app\.main"     "API   " 2
check_family "scripts/dev_worker\.py|\-m app\.worker" "worker" 3
check_family "src/server\.ts"        "render" 2
check_family "vite/bin/vite\.js dev" "web   " 1
if [ "$DEAD" -ne 0 ]; then
  echo "⚠ One or more services failed to start — the environment is NOT whole."
fi

# --- cleanup ---------------------------------------------------------------
# Ctrl+C 也要干净：先杀本次启动的四个 supervisor，再按家族模式清场——包装器死了
# 不保证 spawn 子进程 / watcher 跟着死，也不能让 supervisor 在清场时复活服务。
trap 'echo; echo "Shutting down..."; kill "$API_PID" "$WORKER_PID" "$RENDER_PID" "$WEB_PID" 2>/dev/null; sleep 1; kill_service_families -9; rm -f "$SUPERVISOR_DIR"/*.pid; exit' INT TERM

wait
