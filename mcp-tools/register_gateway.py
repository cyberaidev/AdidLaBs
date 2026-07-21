"""Ensure the AdidLaBs AgentCore Gateway exists and expose the six MCP tools.

Concept demo - no affiliation with adidas AG. All products fictional.

What it does (idempotent, in order):
  1. Ensure the gateway's IAM service role (``adidlabs-gateway-role``): trusted
     by bedrock-agentcore.amazonaws.com, allowed to invoke the tools Lambda.
  2. Ensure the gateway itself (``adidlabs-tools-gw``): MCP protocol with a
     Cognito CUSTOM_JWT authorizer (user-pool discovery URL + app client).
  3. Ensure ONE Lambda target (``adidlabs-tools``) exposing every tool from
     ``server.TOOL_SPECS`` with an inline JSON schema; the gateway routes MCP
     tool calls to the tools Lambda.

Env (deploy.sh passes these from stack outputs):
    TOOLS_FUNCTION_NAME     tools Lambda name (required for real runs)
    USER_POOL_PROVIDER_URL  https://cognito-idp.<region>.amazonaws.com/<pool>
    USER_POOL_CLIENT_ID     Cognito app client id
    AGENTCORE_GATEWAY_ID / GATEWAY_ID   optional pre-existing gateway id

Usage:
    python register_gateway.py                 # ensure gateway + target
    python register_gateway.py --dry-run       # print the plan, call nothing
    python register_gateway.py --gateway-id GW # use an existing gateway

Region: AWS_REGION env, default ap-southeast-2 (Sydney).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Import the single source of truth for the tool surface.
try:
    from server import TOOL_SPECS  # when run from within mcp-tools/
except ImportError:  # pragma: no cover - allow `python mcp-tools/register_gateway.py`
    from mcp_tools.server import TOOL_SPECS  # type: ignore

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")

GATEWAY_NAME = "adidlabs-tools-gw"
TARGET_NAME = "adidlabs-tools"
ROLE_NAME = "adidlabs-gateway-role"

# JSON input schema per tool (MCP inputSchema). Keys must match TOOL_SPECS.
TOOL_INPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "get_catalog": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "One of shoes|pants|tshirt|jumper|jacket|accessory.",
            },
            "query": {"type": "string", "description": "Optional name filter."},
            "limit": {"type": "integer", "description": "Max items (default 10)."},
        },
        "required": [],
    },
    "get_deals": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Optional category filter."},
        },
        "required": [],
    },
    "bag_add": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Cognito user id."},
            "item_id": {"type": "string", "description": "Catalog item id."},
            "qty": {"type": "integer", "description": "Quantity (default 1)."},
        },
        "required": ["user_id", "item_id"],
    },
    "bag_get": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Cognito user id."},
        },
        "required": ["user_id"],
    },
    "search_lab_knowledge": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural-language question."},
            "max_results": {"type": "integer", "description": "Top chunks (default 4)."},
        },
        "required": ["query"],
    },
    "search_web": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Web search query (KB-miss fallback)."},
            "max_results": {"type": "integer", "description": "Max hits (default 5)."},
        },
        "required": ["query"],
    },
}


# --------------------------------------------------------------------------- #
# boto3 client factories (module-level so tests can stub them)
# --------------------------------------------------------------------------- #
def _gateway_client():  # pragma: no cover - thin boto3 wrapper, stubbed in tests
    import boto3

    return boto3.client("bedrock-agentcore-control", region_name=REGION)


def _iam_client():  # pragma: no cover - thin boto3 wrapper, stubbed in tests
    import boto3

    return boto3.client("iam", region_name=REGION)


def _lambda_client():  # pragma: no cover - thin boto3 wrapper, stubbed in tests
    import boto3

    return boto3.client("lambda", region_name=REGION)


def _resolve_gateway_id(explicit: Optional[str]) -> Optional[str]:
    """Pick an EXISTING gateway id from the flag, then env. None means
    'ensure the demo gateway exists and use it'."""
    if explicit:
        return explicit
    return os.environ.get("AGENTCORE_GATEWAY_ID") or os.environ.get("GATEWAY_ID") or None


# --------------------------------------------------------------------------- #
# Payload builders (pure - unit tested)
# --------------------------------------------------------------------------- #
def build_tool_entry(spec: Dict[str, str]) -> Dict[str, Any]:
    """One inlinePayload entry for the Lambda target's tool schema."""
    name = spec["name"]
    return {
        "name": name,
        "description": spec["description"],
        "inputSchema": TOOL_INPUT_SCHEMAS[name],
    }


def build_target_payload(gateway_id: str, tools_fn_arn: str) -> Dict[str, Any]:
    """The create_gateway_target request: one Lambda target, all six tools."""
    return {
        "gatewayIdentifier": gateway_id,
        "name": TARGET_NAME,
        "description": "AdidLaBs MCP tools (catalog, deals, bag, KB retrieve, web search).",
        "targetConfiguration": {
            "mcp": {
                "lambda": {
                    "lambdaArn": tools_fn_arn,
                    "toolSchema": {"inlinePayload": [build_tool_entry(s) for s in TOOL_SPECS]},
                }
            }
        },
        "credentialProviderConfigurations": [
            {"credentialProviderType": "GATEWAY_IAM_ROLE"}
        ],
    }


def _trust_policy(account_id: str) -> Dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:SourceAccount": account_id}},
            }
        ],
    }


def _invoke_policy(tools_fn_arn: str) -> Dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": [tools_fn_arn, f"{tools_fn_arn}:*"],
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Ensure steps (idempotent)
# --------------------------------------------------------------------------- #
def ensure_gateway_role(iam, account_id: str, tools_fn_arn: str) -> str:
    """Get-or-create the gateway service role; keep its policy in sync."""
    from botocore.exceptions import ClientError  # type: ignore

    try:
        arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        created = False
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchEntity":
            raise
        arn = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(_trust_policy(account_id)),
            Description="AdidLaBs AgentCore Gateway service role (concept demo).",
            Tags=[{"Key": "app", "Value": "adidlabs"}],
        )["Role"]["Arn"]
        created = True
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="invoke-tools-lambda",
        PolicyDocument=json.dumps(_invoke_policy(tools_fn_arn)),
    )
    if created:
        print(f"[gw] created role {arn}; waiting for IAM propagation…")
        time.sleep(10)
    else:
        print(f"[gw] role exists: {arn}")
    return arn


def find_gateway_by_name(client, name: str) -> Optional[Dict[str, Any]]:
    paginator = client.get_paginator("list_gateways")
    for page in paginator.paginate():
        for gw in page.get("items", []):
            if gw.get("name") == name:
                return gw
    return None


def ensure_gateway(client, role_arn: str, discovery_url: str,
                   allowed_client: str) -> Tuple[str, str]:
    """Get-or-create the MCP gateway. Returns (gateway_id, gateway_url)."""
    from botocore.exceptions import ClientError  # type: ignore

    existing = find_gateway_by_name(client, GATEWAY_NAME)
    if existing:
        gid = existing.get("gatewayId") or existing.get("gatewayIdentifier")
        print(f"[gw] gateway exists: {gid}")
        detail = client.get_gateway(gatewayIdentifier=gid)
        return gid, detail.get("gatewayUrl", "")

    print(f"[gw] creating gateway: {GATEWAY_NAME}")
    last_exc: Optional[Exception] = None
    for attempt in range(6):  # tolerate IAM role propagation delays
        try:
            resp = client.create_gateway(
                name=GATEWAY_NAME,
                description="AdidLaBs MCP tool gateway (concept demo).",
                roleArn=role_arn,
                protocolType="MCP",
                authorizerType="CUSTOM_JWT",
                authorizerConfiguration={
                    "customJWTAuthorizer": {
                        "discoveryUrl": discovery_url,
                        "allowedClients": [allowed_client],
                    }
                },
            )
            return resp["gatewayId"], resp.get("gatewayUrl", "")
        except ClientError as exc:  # pragma: no cover - retry path
            last_exc = exc
            print(f"[gw] create_gateway attempt {attempt + 1} failed: {exc}; retrying…",
                  file=sys.stderr)
            time.sleep(8)
    raise RuntimeError(f"create_gateway failed after retries: {last_exc}")


def ensure_target(client, gateway_id: str, tools_fn_arn: str) -> str:
    """Get-or-create the single Lambda target carrying all six tools."""
    resp = client.list_gateway_targets(gatewayIdentifier=gateway_id)
    for target in resp.get("items", []):
        if target.get("name") == TARGET_NAME:
            tid = target.get("targetId")
            print(f"[gw] target exists: {tid}")
            return tid
    print(f"[gw] creating target: {TARGET_NAME} -> {tools_fn_arn}")
    created = client.create_gateway_target(**build_target_payload(gateway_id, tools_fn_arn))
    return created.get("targetId", "")


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure the AdidLaBs AgentCore Gateway + MCP tool target.")
    parser.add_argument("--gateway-id", default=None,
                        help="Use an existing AgentCore Gateway id (skip creation).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the plan, call nothing.")
    args = parser.parse_args(argv)

    plan = {
        "gateway": GATEWAY_NAME,
        "target": TARGET_NAME,
        "tools": [build_tool_entry(s) for s in TOOL_SPECS],
    }
    if args.dry_run:
        print(json.dumps({"planned": plan}, indent=2))
        return 0

    tools_fn = os.environ.get("TOOLS_FUNCTION_NAME")
    provider_url = os.environ.get("USER_POOL_PROVIDER_URL")
    client_id = os.environ.get("USER_POOL_CLIENT_ID")
    if not tools_fn or not provider_url or not client_id:
        print("[gw] ERROR: TOOLS_FUNCTION_NAME, USER_POOL_PROVIDER_URL and "
              "USER_POOL_CLIENT_ID are required (stack outputs).", file=sys.stderr)
        return 2

    lam = _lambda_client()
    fn = lam.get_function(FunctionName=tools_fn)["Configuration"]
    tools_fn_arn = fn["FunctionArn"]
    account_id = tools_fn_arn.split(":")[4]
    discovery_url = provider_url.rstrip("/") + "/.well-known/openid-configuration"

    gateway_client = _gateway_client()
    explicit = _resolve_gateway_id(args.gateway_id)
    if explicit:
        gateway_id, gateway_url = explicit, ""
        print(f"[gw] using provided gateway id: {gateway_id}")
    else:
        role_arn = ensure_gateway_role(_iam_client(), account_id, tools_fn_arn)
        gateway_id, gateway_url = ensure_gateway(
            gateway_client, role_arn, discovery_url, client_id)

    target_id = ensure_target(gateway_client, gateway_id, tools_fn_arn)

    print(json.dumps({
        "gateway_id": gateway_id,
        "gateway_url": gateway_url,
        "target_id": target_id,
        "tools": [s["name"] for s in TOOL_SPECS],
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    sys.exit(main())
