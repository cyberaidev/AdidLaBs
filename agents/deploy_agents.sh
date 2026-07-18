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
: "${LITELLM_URL:?set LITELLM_URL to the LiteLLM gateway function URL}"
: "${KB_ID:?set KB_ID (from data/setup_kb.py)}"
: "${CATALOG_TABLE:=adidlabs-catalog}"
: "${BAG_TABLE:=adidlabs-bag}"
: "${AGENTCORE_AGENT_ARN:?set AGENTCORE_AGENT_ARN}"
: "${DEMO_MODE:=0}"
TAVILY_API_KEY="${TAVILY_API_KEY:-}"

cd "${SCRIPT_DIR}"

echo "==> agentcore configure"
agentcore configure \
  --config agentcore.yaml \
  --region "${REGION}"

echo "==> agentcore launch"
agentcore launch \
  --region "${REGION}" \
  --env "LITELLM_URL=${LITELLM_URL}" \
  --env "KB_ID=${KB_ID}" \
  --env "CATALOG_TABLE=${CATALOG_TABLE}" \
  --env "BAG_TABLE=${BAG_TABLE}" \
  --env "AGENTCORE_AGENT_ARN=${AGENTCORE_AGENT_ARN}" \
  --env "DEMO_MODE=${DEMO_MODE}" \
  --env "TAVILY_API_KEY=${TAVILY_API_KEY}"

echo "==> Done. Set the printed runtime ARN as AGENTCORE_AGENT_ARN for api-handler."
