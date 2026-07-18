#!/usr/bin/env bash
# AdidLaBs — build the LiteLLM gateway Lambda zip (AWS Lambda Web Adapter, layer path)
# Concept demo — no affiliation with adidas AG. All products fictional.
#
# Produces gateway/dist/gateway-lambda.zip for infra to deploy as a Python 3.12
# (x86_64) Lambda with the public LWA layer attached. The zip contains:
#   bootstrap            -> exec wrapper the LWA layer invokes on cold start
#   gateway_app.py       -> starts the LiteLLM OpenAI-compatible server
#   config.yaml          -> the two-route config (copied from gateway/config.yaml)
#   python/              -> vendored dependencies (manylinux x86_64, cp312)
#
# Deps are installed for the LAMBDA target platform, not the build host, so the
# zip is portable from macOS/arm64 dev machines. Requires pip >= 22.
#
# Usage:
#   ./build_zip.sh
# Output:
#   gateway/dist/gateway-lambda.zip   (path printed at the end)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"          # gateway/lambda
GATEWAY_DIR="$(cd "${HERE}/.." && pwd)"                        # gateway
BUILD="${HERE}/.build"
DIST="${GATEWAY_DIR}/dist"
ZIP="${DIST}/gateway-lambda.zip"

log()  { printf '\033[1;33m[build_zip]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[build_zip] FAIL:\033[0m %s\n' "$*" >&2; exit 1; }

command -v pip3 >/dev/null 2>&1 || fail "pip3 not found (need Python 3.12 toolchain)."
command -v zip  >/dev/null 2>&1 || fail "zip not found."

log "Cleaning previous build ..."
rm -rf "$BUILD"
mkdir -p "$BUILD/python" "$DIST"

log "Copying application files ..."
cp "${HERE}/bootstrap"       "${BUILD}/bootstrap"
cp "${HERE}/gateway_app.py"  "${BUILD}/gateway_app.py"
cp "${GATEWAY_DIR}/config.yaml" "${BUILD}/config.yaml"
chmod +x "${BUILD}/bootstrap"

log "Vendoring dependencies for the Lambda platform (manylinux2014_x86_64, cp312) ..."
# --platform + --only-binary=:all: forces manylinux wheels so the artifact runs
# on the Lambda runtime regardless of the build host's OS/arch.
pip3 install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --upgrade \
  --target "${BUILD}/python" \
  -r "${HERE}/requirements.txt" \
  || fail "dependency install failed. Ensure pip>=22 and network access to PyPI."

log "Pruning build artifacts to shrink the zip ..."
find "${BUILD}/python" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "${BUILD}/python" -type d -name "*.dist-info" -prune -exec rm -rf {} + 2>/dev/null || true
find "${BUILD}/python" -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true

log "Zipping package ..."
rm -f "$ZIP"
( cd "$BUILD" && zip -qr "$ZIP" . )

SIZE="$(du -h "$ZIP" | cut -f1)"
log "Built ${ZIP} (${SIZE})."

# Resolve the LWA layer ARN rather than printing an unverifiable pinned version.
# resolve_lwa_layer_arn.sh finds the current published version in-region (or
# honours LWA_LAYER_VERSION if you pin one). If it can't run (no aws CLI, offline),
# fall back to a clearly-labelled placeholder the deployer MUST confirm.
LAYER_ARN=""
if [[ -x "${HERE}/resolve_lwa_layer_arn.sh" ]]; then
  LAYER_ARN="$(REGION=ap-southeast-2 ARCH=x86_64 "${HERE}/resolve_lwa_layer_arn.sh" 2>/dev/null || true)"
fi
if [[ -n "$LAYER_ARN" ]]; then
  LAYER_LINE="$LAYER_ARN  (resolved)"
else
  LAYER_LINE="arn:aws:lambda:ap-southeast-2:753240598075:layer:LambdaAdapterLayerX86:<VERSION>  (UNRESOLVED — run resolve_lwa_layer_arn.sh or set LWA_LAYER_VERSION; do not assume a number)"
fi

log "Deploy contract for infra:"
log "  Runtime      : python3.12   Arch: x86_64"
log "  Handler      : bootstrap    (the LWA wrapper execs this script)"
log "  Layer (LWA)  : ${LAYER_LINE}"
log "  Env          : AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap  AWS_LWA_PORT=8000  PORT=8000"
log "  Function URL : AuthType=AWS_IAM   (never public)"
echo "$ZIP"
