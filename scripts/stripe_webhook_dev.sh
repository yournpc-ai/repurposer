#!/bin/bash
# Ensure exactly one company-test Stripe listener forwards to this project's API.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
LOG_FILE="${TMPDIR:-/tmp}/repurposer-stripe-webhook.log"
FORWARD_URL="http://127.0.0.1:8000/api/v1/payments/stripe/webhook"
EVENTS="checkout.session.completed,checkout.session.expired"

fail() {
  echo "✘ $*" >&2
  exit 1
}

command -v stripe >/dev/null 2>&1 || fail "Stripe CLI is missing: brew install stripe/stripe-cli/stripe"
[ -f "$ENV_FILE" ] || fail "Missing $ENV_FILE"

env_value() {
  python3 -I -c 'from pathlib import Path
import sys
path, wanted = sys.argv[1], sys.argv[2]
for raw in Path(path).read_text().splitlines():
    if raw and not raw.lstrip().startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        if key.strip() == wanted:
            print(value.strip())
            break' "$ENV_FILE" "$1"
}

set_env_value() {
  python3 -I -c 'from pathlib import Path
import sys
path, wanted, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = path.read_text().splitlines()
for index, raw in enumerate(lines):
    if raw and not raw.lstrip().startswith("#") and "=" in raw:
        key, _ = raw.split("=", 1)
        if key.strip() == wanted:
            lines[index] = f"{wanted}={value}"
            break
else:
    lines.append(f"{wanted}={value}")
path.write_text("\n".join(lines) + "\n")' "$ENV_FILE" "$1" "$2"
}

API_KEY="$(env_value STRIPE_SECRET_KEY)"
WEBHOOK_SECRET="$(env_value STRIPE_WEBHOOK_SECRET)"
PRICE_ID="$(env_value STRIPE_PRICE_STARTER)"

case "$API_KEY" in
  sk_test_*|rk_test_*) ;;
  *) fail "STRIPE_SECRET_KEY must be a company TEST key; live mode is refused" ;;
esac
case "$WEBHOOK_SECRET" in
  whsec_*|"") ;;
  *) fail "STRIPE_WEBHOOK_SECRET has an invalid format in .env" ;;
esac
case "$PRICE_ID" in
  price_*) ;;
  *) fail "STRIPE_PRICE_STARTER is missing from .env" ;;
esac

# Respect an explicit proxy; otherwise discover the macOS system proxy as the
# render launcher does. Local forwarding always bypasses it.
if [ -z "${HTTPS_PROXY:-${HTTP_PROXY:-${https_proxy:-${http_proxy:-}}}}" ] && command -v scutil >/dev/null 2>&1; then
  SYSTEM_PROXY="$(scutil --proxy | awk '
    $1 == "HTTPSEnable" { enabled=$3 }
    $1 == "HTTPSProxy" { host=$3 }
    $1 == "HTTPSPort" { port=$3 }
    END { if (enabled == 1 && host != "" && port != "") print "http://" host ":" port }
  ')"
  if [ -n "$SYSTEM_PROXY" ]; then
    export HTTPS_PROXY="$SYSTEM_PROXY" HTTP_PROXY="$SYSTEM_PROXY"
  fi
fi
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

# print-secret exits after one authenticated lookup; it never starts a second
# listener. Comparing it here catches stale .env values without exposing either.
CLI_SECRET="$(stripe listen --api-key "$API_KEY" --print-secret 2>/dev/null)" \
  || fail "Could not verify the webhook signing secret through Stripe"
case "$CLI_SECRET" in
  whsec_*) ;;
  *) fail "Stripe CLI returned an invalid signing secret" ;;
esac
if [ -z "$WEBHOOK_SECRET" ]; then
  set_env_value STRIPE_WEBHOOK_SECRET "$CLI_SECRET"
  chmod 600 "$ENV_FILE"
  echo "✔ Generated and saved the local webhook signing secret"
elif [ "$CLI_SECRET" != "$WEBHOOK_SECRET" ]; then
  fail "The CLI signing secret and .env differ; update STRIPE_WEBHOOK_SECRET"
else
  echo "✔ Stripe test configuration and signing secret verified"
fi

PATTERN='stripe listen .*--forward-to http://127\.0\.0\.1:8000/api/v1/payments/stripe/webhook'
PIDS="$(pgrep -f "$PATTERN" 2>/dev/null || true)"
COUNT=0
if [ -n "$PIDS" ]; then
  COUNT="$(printf '%s\n' "$PIDS" | wc -l | tr -d ' ')"
fi

if [ "$COUNT" -gt 1 ]; then
  fail "Multiple listeners target this endpoint (PIDs: $(printf '%s' "$PIDS" | tr '\n' ' ')); stop duplicates before testing"
fi

if [ "$COUNT" -eq 1 ]; then
  LISTENER_COMMAND="$(ps -p "$PIDS" -o command=)"
  case "$LISTENER_COMMAND" in
    *--events*)
      case "$LISTENER_COMMAND" in
        *"$EVENTS"*) ;;
        *) fail "The running listener has a different event filter; restart it with $EVENTS" ;;
      esac
      ;;
    # No --events filter means all events, a valid superset for local testing.
  esac
  echo "✔ Webhook listener is already running (pid $PIDS)"
else
  : > "$LOG_FILE"
  chmod 600 "$LOG_FILE"
  nohup stripe listen \
    --api-key "$API_KEY" \
    --events "$EVENTS" \
    --forward-to "$FORWARD_URL" \
    > "$LOG_FILE" 2>&1 &
  PID=$!

  READY=0
  for ((i=0; i<20; i++)); do
    if grep -q 'Ready!' "$LOG_FILE" 2>/dev/null; then
      READY=1
      break
    fi
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if [ "$READY" -ne 1 ]; then
    kill "$PID" 2>/dev/null || true
    fail "Listener did not become Ready; inspect $LOG_FILE"
  fi
  echo "✔ Webhook listener started and Ready (pid $PID)"
fi

echo "  $FORWARD_URL"
echo "  events: $EVENTS"
if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "✔ Local API is reachable"
else
  echo "⚠ Listener is running, but the local API is not reachable on 127.0.0.1:8000"
fi
