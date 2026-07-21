#!/usr/bin/env bash
#
# AdidLaBs — end-to-end deploy orchestration.
# Concept demo — no affiliation with adidas AG. All products fictional.
#
# Order (real dependency chain):
#   0. prerequisite checks (aws, creds, region, node, python, docker)
#   1. frontend build              (Vite/React → static assets)
#   2. CloudFormation deploy        (S3, CloudFront, Cognito, HTTP API + Lambda,
#                                    DynamoDB, LiteLLM Lambda + IAM function URL,
#                                    AgentCore Runtime + Gateway, IAM roles)
#   3. sync built assets to the site bucket + invalidate CloudFront
#   4. seed catalog                 (HF sample or synthetic_fallback.json → DynamoDB,
#                                    generate markdown corpus → KB bucket)
#   5. setup KB                     (data/setup_kb.py: S3 Vectors index + Bedrock KB,
#                                    ingest corpus, print KB_ID) → push KB_ID to Lambdas
#   6. deploy agents                (register/update AgentCore Runtime agents)
#   7. deploy gateway               (register AgentCore Gateway MCP tool targets)
#   8. print CloudFront / API / LiteLLM URLs
#
# CRITICAL: this script MUST NOT overwrite or delete docs/design.md or
# docs/architecture.md. They are protected inputs. A guard verifies they are
# unchanged on entry and on exit; the script never writes under docs/.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config (override via env)
# ---------------------------------------------------------------------------
REGION="${AWS_REGION:-ap-southeast-2}"
STACK_NAME="${STACK_NAME:-adidlabs}"
TEMPLATE="${TEMPLATE:-infra/template.yaml}"
PARAMS_FILE="${PARAMS_FILE:-infra/params.json}"
DEMO_MODE="${DEMO_MODE:-true}"
CATALOG_TABLE="${CATALOG_TABLE:-adidlabs-catalog}"
BAG_TABLE="${BAG_TABLE:-adidlabs-bag}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Protected inputs — never write/delete these.
PROTECTED=("docs/design.md" "docs/architecture.md")

# ---------------------------------------------------------------------------
# Pretty logging
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
    [ -f "$f" ] || die "Protected input missing before deploy: $f"
    GUARD_SUMS+="$(shasum -a 256 "$f")"$'\n'
  done
}
guard_verify() {
  for f in "${PROTECTED[@]}"; do
    [ -f "$f" ] || die "Protected input was deleted during deploy: $f"
  done
  local now
  now=""
  for f in "${PROTECTED[@]}"; do now+="$(shasum -a 256 "$f")"$'\n'; done
  [ "$now" = "$GUARD_SUMS" ] || die "Protected input changed during deploy (design.md/architecture.md must not be modified)."
  ok "Protected docs intact (design.md, architecture.md)."
}

# ---------------------------------------------------------------------------
# 0. Prerequisite checks
# ---------------------------------------------------------------------------
prereqs() {
  step "0. Prerequisite checks"

  command -v aws  >/dev/null 2>&1 || die "AWS CLI not found. Install AWS CLI v2."
  command -v node >/dev/null 2>&1 || die "Node not found. Install Node >= 20."
  command -v npm  >/dev/null 2>&1 || die "npm not found. Install Node >= 20 (includes npm)."
  command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.12."

  # Node >= 20
  local node_major
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$node_major" -ge 20 ] || die "Node >= 20 required (found $(node -v))."

  # Python >= 3.12
  python3 - <<'PY' || die "Python 3.12+ required."
import sys
raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)
PY

  # Docker is needed to build the LiteLLM container image.
  command -v docker >/dev/null 2>&1 || die "Docker not found. Required to build the LiteLLM container image."
  docker info >/dev/null 2>&1 || die "Docker daemon not reachable. Start Docker and retry."

  # Credentials + region.
  aws sts get-caller-identity >/dev/null 2>&1 || die "AWS credentials not configured or expired. Run 'aws configure' / refresh SSO."
  [ "$REGION" = "ap-southeast-2" ] || die "REGION must be ap-southeast-2 (Sydney); got '$REGION'."
  export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"

  # Expected module inputs (created by their respective creators).
  [ -f "$TEMPLATE" ]        || die "CloudFormation template not found at $TEMPLATE (infra module)."
  [ -d "frontend" ]         || die "frontend/ not found (frontend module)."
  [ -f "data/seed_dynamodb.py" ] || die "data/seed_dynamodb.py not found (data module)."
  [ -f "data/gen_kb_docs.py" ]   || die "data/gen_kb_docs.py not found (data module)."
  [ -f "data/setup_kb.py" ] || die "data/setup_kb.py not found (data module)."

  ok "Prerequisites satisfied · region=$REGION · stack=$STACK_NAME"
}

# ---------------------------------------------------------------------------
# Helper: read a CloudFormation stack output
# ---------------------------------------------------------------------------
cfn_output() {
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text 2>/dev/null
}

# ---------------------------------------------------------------------------
# 1. Frontend build
# ---------------------------------------------------------------------------
build_frontend() {
  step "1. Frontend build (Vite/React)"
  ( cd frontend
    if [ -f package-lock.json ]; then npm ci; else npm install; fi
    npm run build
  )
  [ -d frontend/dist ] || die "frontend/dist not produced by the build."
  ok "Frontend built → frontend/dist"
}

# ---------------------------------------------------------------------------
# 2. CloudFormation deploy
# ---------------------------------------------------------------------------
deploy_cfn() {
  step "2. CloudFormation deploy"
  local param_overrides=( "DemoMode=$DEMO_MODE" "CatalogTable=$CATALOG_TABLE" "BagTable=$BAG_TABLE" )
  if [ -f "$PARAMS_FILE" ]; then
    log "Using parameter file $PARAMS_FILE"
  fi

  # Templates over 51,200 bytes must be uploaded to S3. Keep a small,
  # account/region-scoped deploy bucket for that (cleaned up by teardown.sh).
  local account_id cfn_bucket
  account_id="$(aws sts get-caller-identity --query Account --output text)"
  cfn_bucket="${CFN_BUCKET:-adidlabs-cfn-${account_id}-${REGION}}"
  if ! aws s3api head-bucket --bucket "$cfn_bucket" 2>/dev/null; then
    log "Creating CFN deploy bucket s3://$cfn_bucket"
    aws s3api create-bucket \
      --bucket "$cfn_bucket" \
      --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
    aws s3api put-public-access-block \
      --bucket "$cfn_bucket" \
      --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
  fi

  aws cloudformation deploy \
    --region "$REGION" \
    --stack-name "$STACK_NAME" \
    --template-file "$TEMPLATE" \
    --s3-bucket "$cfn_bucket" \
    --s3-prefix cfn-templates \
    --capabilities CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset \
    --parameter-overrides "${param_overrides[@]}"

  ok "CloudFormation stack '$STACK_NAME' deployed."
}

# ---------------------------------------------------------------------------
# 3. Sync assets + invalidate CloudFront
# ---------------------------------------------------------------------------
sync_assets() {
  step "3. Sync static assets → S3 + invalidate CloudFront"
  local site_bucket dist_id
  site_bucket="$(cfn_output SiteBucketName)"
  dist_id="$(cfn_output CloudFrontDistributionId)"
  [ -n "$site_bucket" ] && [ "$site_bucket" != "None" ] || die "SiteBucketName output missing from stack."

  aws s3 sync frontend/dist "s3://$site_bucket/" --region "$REGION" --delete
  if [ -n "$dist_id" ] && [ "$dist_id" != "None" ]; then
    aws cloudfront create-invalidation --distribution-id "$dist_id" --paths '/*' >/dev/null
    ok "Assets synced to s3://$site_bucket and CloudFront invalidated."
  else
    ok "Assets synced to s3://$site_bucket (no distribution id to invalidate)."
  fi
}

# ---------------------------------------------------------------------------
# 4. Seed catalog (+ generate KB corpus)
# ---------------------------------------------------------------------------
seed_data() {
  step "4. Seed catalog + generate KB corpus"

  # 4a. Seed the DynamoDB catalog table (HF sample or synthetic_fallback.json).
  #     The seeder reads CATALOG_TABLE/AWS_REGION and can create the table
  #     on-demand (PAY_PER_REQUEST) if it is not already present.
  CATALOG_TABLE="$CATALOG_TABLE" \
  AWS_REGION="$REGION" \
    python3 data/seed_dynamodb.py --table "$CATALOG_TABLE" --region "$REGION" --create-table
  ok "Catalog seeded into DynamoDB '$CATALOG_TABLE' (HF sample or synthetic_fallback.json)."

  # 4b. Generate the markdown KB corpus into data/kb_docs/. This is a required
  #     step: seed_dynamodb.py does NOT emit any corpus, and setup_kb.py (step 5)
  #     uploads data/kb_docs/ verbatim — if we skip this the KB ingests nothing
  #     and search_lab_knowledge (RAG) returns empty.
  AWS_REGION="$REGION" \
    python3 data/gen_kb_docs.py --out data/kb_docs
  [ -d data/kb_docs ] || die "gen_kb_docs.py did not produce data/kb_docs (KB corpus)."
  # Guard against an empty corpus dir (would silently break RAG downstream).
  if ! find data/kb_docs -type f -name '*.md' -print -quit | grep -q .; then
    die "KB corpus data/kb_docs contains no markdown; setup_kb.py would ingest nothing."
  fi
  ok "KB corpus generated → data/kb_docs (markdown; setup_kb.py will upload it)."
}

# ---------------------------------------------------------------------------
# 5. Setup Knowledge Base (boto3, preview S3 Vectors) → capture KB_ID
# ---------------------------------------------------------------------------
setup_kb() {
  step "5. Setup Bedrock Knowledge Base over S3 Vectors"
  local kb_id kb_role_arn corpus_bucket
  # The corpus bucket is created by CloudFormation (KbCorpusBucket) and the KB
  # service role's S3 grants are scoped to that exact bucket — pass the stack
  # output through so setup_kb.py can never derive a divergent name. The KB
  # role ARN: prefer an explicit KB_ROLE_ARN, else the KbRoleArn stack output.
  kb_role_arn="${KB_ROLE_ARN:-$(cfn_output KbRoleArn)}"
  corpus_bucket="$(cfn_output KbCorpusBucketName)"
  [ -n "$corpus_bucket" ] || die "KbCorpusBucketName stack output missing."

  # setup_kb.py provisions the vector index + KB, ingests data/kb_docs/, and
  # prints the KB id as the last line of stdout.
  kb_id="$(
    KB_ROLE_ARN="${kb_role_arn:-}" \
    AWS_REGION="$REGION" \
      python3 data/setup_kb.py --region "$REGION" --docs-dir data/kb_docs \
        --corpus-bucket "$corpus_bucket" | tee /dev/stderr | tail -n 1
  )"
  [ -n "$kb_id" ] || die "setup_kb.py did not return a KB_ID."
  export KB_ID="$kb_id"
  ok "Knowledge Base ready · KB_ID=$KB_ID"

  # Push KB_ID onto the API + agent Lambdas (env var name is exactly KB_ID).
  local api_fn agent_fn
  api_fn="$(cfn_output ApiHandlerFunctionName)"
  agent_fn="$(cfn_output ToolsFunctionName)"
  for fn in "$api_fn" "$agent_fn"; do
    [ -n "$fn" ] && [ "$fn" != "None" ] || continue
    log "Setting KB_ID on Lambda $fn"
    local existing
    existing="$(aws lambda get-function-configuration --function-name "$fn" --region "$REGION" \
                 --query 'Environment.Variables' --output json 2>/dev/null || echo '{}')"
    local merged
    merged="$(KB_ID="$KB_ID" python3 - "$existing" <<'PY'
import json, os, sys
env = json.loads(sys.argv[1] or "{}") or {}
env["KB_ID"] = os.environ["KB_ID"]
print(json.dumps({"Variables": env}))
PY
)"
    aws lambda update-function-configuration \
      --function-name "$fn" --region "$REGION" \
      --environment "$merged" >/dev/null
  done
  ok "KB_ID propagated to Lambda environment(s)."
}

# ---------------------------------------------------------------------------
# 6. Deploy agents (AgentCore Runtime)
# ---------------------------------------------------------------------------
deploy_agents() {
  step "6. Deploy AgentCore agents"

  # agents/deploy_agents.sh runs the bedrock-agentcore starter toolkit
  # (configure + launch), creating or updating the runtime, and prints the
  # runtime ARN as its LAST stdout line — the ARN does not exist before
  # launch, so it is an output of this stage, never an input.
  [ -f agents/deploy_agents.sh ] || die "agents/deploy_agents.sh not found (agents module) — cannot deploy the agent mesh."

  local runtime_arn
  runtime_arn="$(
    LITELLM_URL="$(cfn_output LiteLLMUrl)" \
    KB_ID="${KB_ID:-}" \
    CATALOG_TABLE="$CATALOG_TABLE" BAG_TABLE="$BAG_TABLE" \
    DEMO_MODE=0 \
    AWS_REGION="$REGION" \
      bash agents/deploy_agents.sh | tee /dev/stderr | tail -n 1
  )"
  [ -n "$runtime_arn" ] || die "deploy_agents.sh did not return a runtime ARN."

  # Point /api/chat at the live mesh: AGENTCORE_AGENT_ARN set, DEMO_MODE off.
  local api_fn existing merged
  api_fn="$(cfn_output ApiHandlerFunctionName)"
  if [ -n "$api_fn" ] && [ "$api_fn" != "None" ]; then
    log "Setting AGENTCORE_AGENT_ARN on Lambda $api_fn"
    existing="$(aws lambda get-function-configuration --function-name "$api_fn" --region "$REGION" \
                 --query 'Environment.Variables' --output json 2>/dev/null || echo '{}')"
    merged="$(AGENTCORE_AGENT_ARN="$runtime_arn" python3 - "$existing" <<'PY'
import json, os, sys
env = json.loads(sys.argv[1] or "{}") or {}
env["AGENTCORE_AGENT_ARN"] = os.environ["AGENTCORE_AGENT_ARN"]
env["DEMO_MODE"] = "0"
print(json.dumps({"Variables": env}))
PY
)"
    aws lambda update-function-configuration \
      --function-name "$api_fn" --region "$REGION" \
      --environment "$merged" >/dev/null
  fi
  ok "Agents registered/updated on AgentCore Runtime · $runtime_arn"
}

# ---------------------------------------------------------------------------
# 7. Deploy gateway (AgentCore Gateway MCP tool targets)
# ---------------------------------------------------------------------------
deploy_gateway() {
  step "7. Deploy AgentCore Gateway (MCP tool targets)"

  # The MCP tools module registers each tool as an AgentCore Gateway target via
  # mcp-tools/register_gateway.py (it reads the canonical TOOL_SPECS from
  # mcp-tools/server.py). This mandated stage MUST run — registering the six MCP
  # targets is what makes the tools discoverable to the mesh.
  [ -f mcp-tools/register_gateway.py ] || die "mcp-tools/register_gateway.py not found (mcp-tools module) — cannot register gateway targets."

  # register_gateway.py imports server.py (FastMCP), so its deps must be on
  # the active python3 — install them quietly and idempotently.
  python3 -m pip install -q -r mcp-tools/requirements.txt

  # register_gateway.py ensures the gateway (Cognito CUSTOM_JWT authorizer +
  # service role) and one Lambda target carrying all six tools. It needs the
  # tools Lambda name and the Cognito issuer/client from the stack outputs.
  # Gateway id resolves from AGENTCORE_GATEWAY_ID (CFN output if present) →
  # GATEWAY_ID → ensure-and-use the demo gateway.
  local gateway_id
  gateway_id="$(cfn_output AgentGatewayId)"
  ( cd mcp-tools
    TOOLS_FUNCTION_NAME="$(cfn_output ToolsFunctionName)" \
    USER_POOL_PROVIDER_URL="$(cfn_output UserPoolProviderUrl)" \
    USER_POOL_CLIENT_ID="$(cfn_output UserPoolClientId)" \
    LITELLM_URL="$(cfn_output LiteLLMUrl)" \
    KB_ID="${KB_ID:-}" \
    CATALOG_TABLE="$CATALOG_TABLE" BAG_TABLE="$BAG_TABLE" \
    TAVILY_API_KEY="${TAVILY_API_KEY:-}" \
    AGENTCORE_GATEWAY_ID="${gateway_id:-}" \
    AWS_REGION="$REGION" \
      python3 register_gateway.py
  )
  ok "Gateway MCP tool targets registered (get_catalog, get_deals, bag_add, bag_get, search_lab_knowledge, search_web)."
}

# ---------------------------------------------------------------------------
# 8. Print URLs
# ---------------------------------------------------------------------------
print_urls() {
  step "8. Deployment complete"
  local site_url api_url litellm_url
  site_url="$(cfn_output CloudFrontUrl)"
  api_url="$(cfn_output ApiBaseUrl)"
  litellm_url="$(cfn_output LiteLLMUrl)"

  printf '\n'
  printf '  ADIDLABS is deployed in %s\n\n' "$REGION"
  printf '  Site (CloudFront) : %s\n' "${site_url:-<not exported>}"
  printf '  API base          : %s\n' "${api_url:-<not exported>}"
  printf '  LiteLLM URL       : %s  (IAM-auth)\n' "${litellm_url:-<not exported>}"
  printf '  KB_ID             : %s\n' "${KB_ID:-<unset>}"
  printf '\n  Concept demo — no affiliation with adidas AG. All products fictional.\n\n'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  log "Starting AdidLaBs deploy · region=$REGION"
  guard_snapshot
  prereqs
  build_frontend
  deploy_cfn
  sync_assets
  seed_data
  setup_kb
  deploy_agents
  deploy_gateway
  guard_verify
  print_urls
  ok "Done."
}

main "$@"
