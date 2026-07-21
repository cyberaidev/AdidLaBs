#!/usr/bin/env bash
# Deploy the AdidLaBs agent mesh to Bedrock AgentCore via the starter toolkit.
# Concept demo - no affiliation with adidas AG. All products fictional.
#
# Prereqs:
#   * AWS credentials for ap-southeast-2 (Sydney) with AgentCore + ECR perms.
#   * pip install bedrock-agentcore-starter-toolkit
#   * The durable stack (CloudFormation) already deployed so the env values
#     below (LITELLM_URL, KB_ID, table names, agent ARN) exist.
#
# What it does:
#   1. Verifies the entrypoint imports and the LangGraph graph compiles.
#   2. `agentcore configure` from agentcore.yaml.
#   3. `agentcore launch` to build/push the container and create/update the
#      runtime in ap-southeast-2, passing the required env vars.
#
# Usage:
#   ./deploy_agents.sh          # full configure + launch
#   ./deploy_agents.sh --check  # only run the pre-deploy import/compile check

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REGION="ap-southeast-2"

echo "==> AdidLaBs agent deploy (region: ${REGION})"

# 1. Pre-deploy verification: entrypoint imports + graph compiles. No live
#    Bedrock/gateway needed thanks to the in-process fallbacks.
echo "==> Verifying entrypoint loads and graph compiles..."
python -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/..')
from agents.entrypoint import app, ORCHESTRATOR
compiled = ORCHESTRATOR.compile()
assert compiled is not None, 'graph failed to compile'
# Smoke a rain turn to prove the mesh runs end to end.
out = ORCHESTRATOR.run('what should I wear', forecast={'daily': {'time': ['2026-07-18'], 'weathercode': [61], 'temperature_2m_max': [14.0], 'temperature_2m_min': [9.0]}})
assert 'jacket' in out['routed'] and 'accessory' in out['routed'], out['routed']
print('   ok: entrypoint app =', type(app).__name__, '| routed(rain) =', out['routed'])
"

if [[ "${1:-}" == "--check" ]]; then
  echo "==> --check only; skipping deploy."
  exit 0
fi

# Required env for the runtime. Fail early if unset (except optional ones).
# NOTE: AGENTCORE_AGENT_ARN is an OUTPUT of `agentcore launch` — the runtime
# does not exist before launch — so it is never required as an input here.
# This script prints the resolved ARN as its LAST stdout line; deploy.sh
# captures it and pushes it onto the chat Lambda.
: "${LITELLM_URL:?set LITELLM_URL to the LiteLLM gateway function URL}"
: "${KB_ID:?set KB_ID (from data/setup_kb.py)}"
: "${CATALOG_TABLE:=adidlabs-catalog}"
: "${BAG_TABLE:=adidlabs-bag}"
: "${DEMO_MODE:=0}"
TAVILY_API_KEY="${TAVILY_API_KEY:-}"

# AgentCore runtime names must match [a-zA-Z][a-zA-Z0-9_]* — no dashes.
RUNTIME_NAME="adidlabs_agents"

command -v agentcore >/dev/null 2>&1 \
  || { echo "agentcore CLI not found: pip install bedrock-agentcore-starter-toolkit" >&2; exit 1; }

cd "${SCRIPT_DIR}"

export AGENTCORE_SUPPRESS_RECOMMENDATION=1

echo "==> agentcore configure (${RUNTIME_NAME})"
# direct_code_deploy pushes the Python code straight to the runtime — no
# CodeBuild, no ECR, fewest IAM requirements. --non-interactive auto-creates
# the execution role and staging bucket.
agentcore configure \
  --entrypoint entrypoint.py \
  --name "${RUNTIME_NAME}" \
  --requirements-file requirements.txt \
  --region "${REGION}" \
  --deployment-type direct_code_deploy \
  --non-interactive \
  --disable-otel

echo "==> agentcore launch"
LAUNCH_ENVS=(
  --env "LITELLM_URL=${LITELLM_URL}"
  --env "KB_ID=${KB_ID}"
  --env "CATALOG_TABLE=${CATALOG_TABLE}"
  --env "BAG_TABLE=${BAG_TABLE}"
  --env "DEMO_MODE=${DEMO_MODE}"
)
[ -n "${TAVILY_API_KEY}" ] && LAUNCH_ENVS+=( --env "TAVILY_API_KEY=${TAVILY_API_KEY}" )
[ -n "${LITELLM_API_KEY:-}" ] && LAUNCH_ENVS+=( --env "LITELLM_API_KEY=${LITELLM_API_KEY}" )
agentcore launch --auto-update-on-conflict "${LAUNCH_ENVS[@]}"

# Resolve the runtime ARN via boto3 (aws-cli builds older than mid-2025 lack
# the bedrock-agentcore-control commands) and print it as the LAST line.
RUNTIME_ARN="$(AWS_REGION="${REGION}" RUNTIME_NAME="${RUNTIME_NAME}" python3 - <<'PY'
import os
import boto3
client = boto3.client("bedrock-agentcore-control", region_name=os.environ["AWS_REGION"])
name = os.environ["RUNTIME_NAME"]
arn = ""
paginator = client.get_paginator("list_agent_runtimes")
for page in paginator.paginate():
    for runtime in page.get("agentRuntimes", []):
        if runtime.get("agentRuntimeName") == name:
            arn = runtime.get("agentRuntimeArn", "")
print(arn)
PY
)"
[ -n "${RUNTIME_ARN}" ] || { echo "Could not resolve runtime ARN for ${RUNTIME_NAME}" >&2; exit 1; }
echo "==> Runtime ready: ${RUNTIME_ARN}"
echo "${RUNTIME_ARN}"
