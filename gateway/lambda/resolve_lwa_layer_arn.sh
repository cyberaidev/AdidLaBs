#!/usr/bin/env bash
# AdidLaBs — resolve the current AWS Lambda Web Adapter (LWA) layer ARN
# Concept demo — no affiliation with adidas AG. All products fictional.
#
# WHY THIS EXISTS
# The LWA layer version bumps with every adapter release, and the public account
# does NOT grant lambda:ListLayerVersions, so a version number hardcoded in docs
# cannot be trusted to still be valid. Rather than pin an unverifiable ":NN",
# resolve the latest published version at deploy time and let infra consume it.
#
# HOW IT RESOLVES (in order)
#   1. If LWA_LAYER_VERSION is exported, use exactly that (manual override /
#      air-gapped deploys). No AWS call is made.
#   2. Otherwise call `aws lambda get-layer-version-by-arn` walking versions down
#      from a ceiling to find the highest version that actually exists in-region.
#      get-layer-version-by-arn only needs GetLayerVersion (public), unlike
#      ListLayerVersions which the public account does not allow.
#
# The layer is published by the public AWS account 753240598075 in every
# commercial region under the name below.
#
# Usage:
#   ./resolve_lwa_layer_arn.sh                    # x86_64 in ap-southeast-2
#   ARCH=arm64 ./resolve_lwa_layer_arn.sh         # arm64 variant
#   REGION=ap-southeast-1 ./resolve_lwa_layer_arn.sh
#   LWA_LAYER_VERSION=28 ./resolve_lwa_layer_arn.sh   # pin explicitly, skip lookup
#
# Prints the fully-qualified layer ARN on stdout (nothing else), so infra can:
#   LAYER_ARN="$(gateway/lambda/resolve_lwa_layer_arn.sh)"

set -euo pipefail

REGION="${REGION:-${AWS_REGION:-ap-southeast-2}}"
ARCH="${ARCH:-x86_64}"                       # x86_64 | arm64
LWA_ACCOUNT="753240598075"                   # public account hosting the layers

case "$ARCH" in
  x86_64) LAYER_NAME="LambdaAdapterLayerX86" ;;
  arm64)  LAYER_NAME="LambdaAdapterLayerArm64" ;;
  *) printf 'resolve_lwa_layer_arn: unknown ARCH %q (want x86_64 or arm64)\n' "$ARCH" >&2; exit 2 ;;
esac

BASE_ARN="arn:aws:lambda:${REGION}:${LWA_ACCOUNT}:layer:${LAYER_NAME}"

# 1) Explicit override — no AWS call, fully deterministic.
if [[ -n "${LWA_LAYER_VERSION:-}" ]]; then
  printf '%s:%s\n' "$BASE_ARN" "$LWA_LAYER_VERSION"
  exit 0
fi

# 2) Discover the highest existing version via GetLayerVersion (public perm).
command -v aws >/dev/null 2>&1 || {
  printf 'resolve_lwa_layer_arn: aws CLI not found and LWA_LAYER_VERSION not set.\n' >&2
  printf 'Set LWA_LAYER_VERSION=<n> to pin a known-good version, e.g. LWA_LAYER_VERSION=28.\n' >&2
  exit 3
}

# Ceiling to walk down from. Override with LWA_VERSION_CEILING if the adapter has
# shipped many more releases than this default.
CEILING="${LWA_VERSION_CEILING:-60}"
for (( v=CEILING; v>=1; v-- )); do
  if aws lambda get-layer-version-by-arn \
        --region "$REGION" \
        --arn "${BASE_ARN}:${v}" \
        --query 'LayerVersionArn' --output text >/dev/null 2>&1; then
    printf '%s:%s\n' "$BASE_ARN" "$v"
    exit 0
  fi
done

printf 'resolve_lwa_layer_arn: no existing version found for %s in %s (searched 1..%s).\n' \
  "$LAYER_NAME" "$REGION" "$CEILING" >&2
printf 'Confirm the layer name/region, or pin LWA_LAYER_VERSION=<n> manually.\n' >&2
exit 4
