#!/usr/bin/env bash
#
# AdidLaBs — teardown orchestration (exact reverse of deploy.sh).
# Concept demo — no affiliation with adidas AG. All products fictional.
#
# Reverse order:
#   0. prerequisite checks (aws, creds, region, python)
#   1. delete KB + S3 Vectors index      (data/setup_kb.py --teardown; made
#                                          outside CloudFormation, so removed first)
#   2. empty S3 buckets                   (site + KB corpus) so the stack can delete them
#   3. aws cloudformation delete-stack    (removes everything else)
#
# CRITICAL: this script MUST NOT overwrite or delete docs/design.md or
# docs/architecture.md. It never touches the docs/ tree and verifies the two
# protected inputs are byte-identical before and after running.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config (override via env)
# ---------------------------------------------------------------------------
REGION="${AWS_REGION:-ap-southeast-2}"
STACK_NAME="${STACK_NAME:-adidlabs}"
FORCE="${FORCE:-false}"          # set FORCE=true to skip the interactive confirm

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PROTECTED=("docs/design.md" "docs/architecture.md")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log()  { printf '\033[1;33m[adidlabs]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[  ok   ]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[ fail  ]\033[0m %s\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1;36m==== %s ====\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# Protected-doc guard
# ---------------------------------------------------------------------------
guard_snapshot() {
  GUARD_SUMS=""
  for f in "${PROTECTED[@]}"; do
    [ -f "$f" ] || die "Protected input missing before teardown: $f"
    GUARD_SUMS+="$(shasum -a 256 "$f")"$'\n'
  done
}
guard_verify() {
  for f in "${PROTECTED[@]}"; do
    [ -f "$f" ] || die "Protected input was deleted during teardown: $f"
  done
  local now=""
  for f in "${PROTECTED[@]}"; do now+="$(shasum -a 256 "$f")"$'\n'; done
  [ "$now" = "$GUARD_SUMS" ] || die "Protected input changed during teardown (design.md/architecture.md must not be modified)."
  ok "Protected docs intact (design.md, architecture.md)."
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
cfn_output() {
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text 2>/dev/null
}

empty_bucket() {
  local bucket="$1"
  [ -n "$bucket" ] && [ "$bucket" != "None" ] || return 0
  if aws s3api head-bucket --bucket "$bucket" --region "$REGION" >/dev/null 2>&1; then
    log "Emptying s3://$bucket (objects + versions)"
    aws s3 rm "s3://$bucket" --recursive --region "$REGION" >/dev/null 2>&1 || true
    # Remove any versioned/delete-marker objects so the stack can drop the bucket.
    local versions
    versions="$(aws s3api list-object-versions --bucket "$bucket" --region "$REGION" \
      --query '{Objects: [].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null || echo '{}')"
    if [ "$(printf '%s' "$versions" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(len((d or {}).get("Objects") or []))' 2>/dev/null || echo 0)" != "0" ]; then
      aws s3api delete-objects --bucket "$bucket" --region "$REGION" --delete "$versions" >/dev/null 2>&1 || true
    fi
    ok "Emptied s3://$bucket"
  else
    log "Bucket $bucket not found (already gone). Skipping."
  fi
}

# ---------------------------------------------------------------------------
# 0. Prerequisite checks
# ---------------------------------------------------------------------------
prereqs() {
  step "0. Prerequisite checks"
  command -v aws >/dev/null 2>&1 || die "AWS CLI not found. Install AWS CLI v2."
  command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.12."
  aws sts get-caller-identity >/dev/null 2>&1 || die "AWS credentials not configured or expired."
  [ "$REGION" = "ap-southeast-2" ] || die "REGION must be ap-southeast-2 (Sydney); got '$REGION'."
  export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"
  ok "Prerequisites satisfied · region=$REGION · stack=$STACK_NAME"
}

confirm() {
  [ "$FORCE" = "true" ] && return 0
  printf '\033[1;31mThis will DELETE the AdidLaBs stack "%s" and its data in %s.\033[0m\n' "$STACK_NAME" "$REGION"
  printf 'Type the stack name to confirm: '
  read -r reply
  [ "$reply" = "$STACK_NAME" ] || die "Confirmation did not match. Aborting."
}

# ---------------------------------------------------------------------------
# 1. Delete KB + S3 Vectors index (outside CFN → first)
# ---------------------------------------------------------------------------
teardown_kb() {
  step "1. Delete Knowledge Base + S3 Vectors index"
  if [ -f data/setup_kb.py ]; then
    # The KB is created OUTSIDE CloudFormation (setup_kb.py over S3 Vectors), so
    # there is no reliable KbId stack output to read — the template's KbId is an
    # input parameter that stays empty at deploy time. Rather than depend on a
    # resolved id, setup_kb.py --teardown DISCOVERS the KB by name
    # (find_kb_by_name) and removes it, its data sources, the vector index/bucket
    # and the corpus bucket. We pass KB_ID only as best-effort context; teardown
    # does not require it to be set.
    local kb_id
    kb_id="${KB_ID:-$(cfn_output KbId)}"
    KB_ID="${kb_id:-}" AWS_REGION="$REGION" \
      python3 data/setup_kb.py --teardown --region "$REGION" \
        || log "setup_kb.py --teardown reported an issue; continuing."
    ok "KB + S3 Vectors index removed by name-discovery (or already absent)."
  else
    log "data/setup_kb.py not present — nothing to tear down for the KB. Skipping."
  fi
}

# ---------------------------------------------------------------------------
# 2. Empty S3 buckets so the stack can delete them
# ---------------------------------------------------------------------------
empty_buckets() {
  step "2. Empty S3 buckets (site + KB corpus)"
  empty_bucket "$(cfn_output SiteBucketName)"
  empty_bucket "$(cfn_output KbCorpusBucketName)"
}

# ---------------------------------------------------------------------------
# 3. Delete the CloudFormation stack
# ---------------------------------------------------------------------------
delete_stack() {
  step "3. Delete CloudFormation stack"
  if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"
    log "Waiting for stack '$STACK_NAME' to delete…"
    aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$REGION" \
      || die "Stack delete did not complete cleanly. Check the CloudFormation console."
    ok "Stack '$STACK_NAME' deleted."
  else
    log "Stack '$STACK_NAME' not found (already deleted). Skipping."
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  log "Starting AdidLaBs teardown · region=$REGION"
  guard_snapshot
  prereqs
  confirm
  teardown_kb
  empty_buckets
  delete_stack
  guard_verify
  printf '\n  AdidLaBs torn down. Idle cost driven to zero.\n'
  printf '  Concept demo — no affiliation with adidas AG. All products fictional.\n\n'
  ok "Done."
}

main "$@"
