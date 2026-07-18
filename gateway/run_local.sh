#!/usr/bin/env bash
# AdidLaBs — local LiteLLM smoke test
# Concept demo — no affiliation with adidas AG. All products fictional.
#
# Starts LiteLLM locally with gateway/config.yaml and proves BOTH named routes
# ("nova-pro", "haiku-4.5") resolve end-to-end against Bedrock in ap-southeast-2,
# using the OpenAI-compatible /chat/completions surface — exactly how the agents
# call it. Exits non-zero if either route fails.
#
# Prereqs:
#   - Python 3.12 with: pip install 'litellm[proxy]==1.61.20' boto3
#   - AWS credentials in the shell with bedrock:InvokeModel on the two APAC
#     inference profiles, in region ap-southeast-2. e.g.:
#       export AWS_PROFILE=adidlabs
#       export AWS_REGION=ap-southeast-2
#   - Bedrock model access enabled for Nova Pro and Claude Haiku 4.5 in Sydney.
#
# Usage:
#   ./run_local.sh              # start proxy, test both routes, tear down
#   PORT=4001 ./run_local.sh    # override port
#
# Master-key mode (optional): if LITELLM_MASTER_KEY is exported, this script
# ALSO uncomments general_settings.master_key for the local run and sends
#   Authorization: Bearer $LITELLM_MASTER_KEY
# on every call — so the README's "add a master key" step is actually testable.
# With no LITELLM_MASTER_KEY set, it runs keyless exactly as the demo default.
#   LITELLM_MASTER_KEY='sk-demo-local' ./run_local.sh   # prove auth works

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${HERE}/config.yaml"
PORT="${PORT:-4000}"
HOST="127.0.0.1"
BASE="http://${HOST}:${PORT}"
export AWS_REGION="${AWS_REGION:-ap-southeast-2}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-$AWS_REGION}"

# Optional application-level auth. Empty by default (keyless demo). When set,
# auth_curl_args expands to the curl -H flag; when unset it expands to nothing.
# We wrap the expansion (see auth_curl) so an empty array is safe under `set -u`
# on macOS's default bash 3.2.
MASTER_KEY="${LITELLM_MASTER_KEY:-}"
AUTH_HEADER=()
[[ -n "$MASTER_KEY" ]] && AUTH_HEADER=(-H "Authorization: Bearer ${MASTER_KEY}")

# curl wrapper that always includes the (possibly empty) auth header safely.
auth_curl() { curl "${AUTH_HEADER[@]+"${AUTH_HEADER[@]}"}" "$@"; }

log()  { printf '\033[1;33m[run_local]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[run_local] FAIL:\033[0m %s\n' "$*" >&2; exit 1; }

command -v litellm >/dev/null 2>&1 || fail "litellm not found. Run: pip install 'litellm[proxy]==1.61.20'"
command -v curl    >/dev/null 2>&1 || fail "curl not found."
[[ -f "$CONFIG" ]] || fail "config not found at $CONFIG"

log "Region: $AWS_REGION"

# Choose the config to launch with. Keyless by default. In master-key mode we
# materialise a temp copy with general_settings.master_key enabled so the proxy
# actually enforces the Bearer token — otherwise "auth works" would be untested.
RUN_CONFIG="$CONFIG"
TMP_CONFIG=""
if [[ -n "$MASTER_KEY" ]]; then
  log "Master-key mode: LITELLM_MASTER_KEY is set — enabling auth for this run."
  TMP_CONFIG="$(mktemp -t adidlabs-litellm-config.XXXXXX.yaml)"
  cp "$CONFIG" "$TMP_CONFIG"
  # Enable master_key regardless of whether the source line is commented or absent.
  if grep -qE '^[[:space:]]*#?[[:space:]]*master_key:' "$TMP_CONFIG"; then
    # Uncomment/normalise the existing (commented) master_key line.
    sed -i.bak -E 's|^[[:space:]]*#?[[:space:]]*master_key:.*$|  master_key: os.environ/LITELLM_MASTER_KEY|' "$TMP_CONFIG"
    rm -f "${TMP_CONFIG}.bak"
  elif grep -qE '^general_settings:' "$TMP_CONFIG"; then
    # Section exists but no master_key line — append the key under it.
    printf '  master_key: os.environ/LITELLM_MASTER_KEY\n' >> "$TMP_CONFIG"
  else
    # No general_settings section at all — add one.
    printf '\ngeneral_settings:\n  master_key: os.environ/LITELLM_MASTER_KEY\n' >> "$TMP_CONFIG"
  fi
  export LITELLM_MASTER_KEY="$MASTER_KEY"   # resolved by os.environ/LITELLM_MASTER_KEY
  RUN_CONFIG="$TMP_CONFIG"
else
  log "Keyless mode (demo default): no master key, no auth header on calls."
fi

log "Config: $RUN_CONFIG"
log "Starting LiteLLM proxy on ${BASE} ..."

litellm --config "$RUN_CONFIG" --host "$HOST" --port "$PORT" >/tmp/adidlabs-litellm.log 2>&1 &
PROXY_PID=$!

cleanup() {
  log "Stopping proxy (pid $PROXY_PID) ..."
  kill "$PROXY_PID" >/dev/null 2>&1 || true
  wait "$PROXY_PID" 2>/dev/null || true
  if [[ -n "$TMP_CONFIG" && -f "$TMP_CONFIG" ]]; then
    rm -f "$TMP_CONFIG"
  fi
}
trap cleanup EXIT

# Wait for the proxy health endpoint to come up.
log "Waiting for proxy to become healthy ..."
for i in $(seq 1 30); do
  if curl -fsS "${BASE}/health/liveliness" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$PROXY_PID" 2>/dev/null; then
    cat /tmp/adidlabs-litellm.log >&2 || true
    fail "proxy process died during startup (see log above)."
  fi
  sleep 1
  [[ "$i" == "30" ]] && { cat /tmp/adidlabs-litellm.log >&2 || true; fail "proxy did not become healthy in 30s."; }
done
log "Proxy is up."

# Confirm the config exposes EXACTLY the two expected route names and no more.
# In master-key mode the Authorization header is required here — /v1/models is
# an authenticated route — so sending it also proves the key is accepted.
log "Verifying route names via ${BASE}/v1/models ..."
MODELS_JSON="$(auth_curl -fsS "${BASE}/v1/models")" || fail "could not read /v1/models (auth rejected? check LITELLM_MASTER_KEY)"
echo "$MODELS_JSON" | grep -q '"nova-pro"'  || fail 'route "nova-pro" missing from /v1/models'
echo "$MODELS_JSON" | grep -q '"haiku-4.5"' || fail 'route "haiku-4.5" missing from /v1/models'
# Count route entries (each model id appears once in the "data" array).
ROUTE_COUNT="$(printf '%s' "$MODELS_JSON" | tr ',' '\n' | grep -c '"id"' || true)"
[[ "$ROUTE_COUNT" == "2" ]] || fail "expected exactly 2 routes, /v1/models reports $ROUTE_COUNT"
log "Found exactly 2 routes: nova-pro, haiku-4.5."

# Helper: call a route with a tiny prompt and assert a non-empty completion.
test_route() {
  local route="$1"
  log "Testing route '${route}' via POST /chat/completions ..."
  local resp
  resp="$(auth_curl -fsS "${BASE}/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{
          \"model\": \"${route}\",
          \"messages\": [{\"role\": \"user\", \"content\": \"Reply with exactly the word: OK\"}],
          \"max_tokens\": 16,
          \"temperature\": 0
        }")" || fail "route '${route}' request failed (see /tmp/adidlabs-litellm.log)"

  # Extract the assistant content without a JSON dependency.
  local content
  content="$(printf '%s' "$resp" | python3 -c 'import sys,json;print(json.load(sys.stdin)["choices"][0]["message"]["content"].strip())' 2>/dev/null || true)"
  [[ -n "$content" ]] || { printf '%s\n' "$resp" >&2; fail "route '${route}' returned no content"; }
  log "Route '${route}' OK → \"${content}\""
}

test_route "nova-pro"
test_route "haiku-4.5"

if [[ -n "$MASTER_KEY" ]]; then
  log "SUCCESS: both routes resolved AND master-key auth was accepted on every call."
else
  log "SUCCESS: both routes resolved and returned valid responses."
fi
log "Full proxy log at /tmp/adidlabs-litellm.log"
