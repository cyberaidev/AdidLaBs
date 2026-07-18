"""Register the AdidLaBs MCP tools server as an AgentCore Gateway target.

Concept demo - no affiliation with adidas AG. All products fictional.

The AgentCore Gateway exposes an MCP surface to the agent mesh. This script
registers each of the six tools (from ``server.TOOL_SPECS``) as a gateway
*target* so the orchestrator and category agents can discover and call them.

It is idempotent-ish: it enumerates the canonical TOOL_SPECS and issues one
`create_gateway_target` call per tool against the gateway resolved by
``_resolve_gateway_id``: the ``--gateway-id`` flag, then the
``AGENTCORE_GATEWAY_ID`` env var, then the ``GATEWAY_ID`` env var, and finally a
stable demo default of ``adidlabs-tools-gw``. The gateway id is deliberately
*not* derived from ``AGENTCORE_AGENT_ARN``. All AWS I/O goes through
``_gateway_client`` so tests can stub it.

Usage:
    python register_gateway.py                 # register all tools
    python register_gateway.py --dry-run       # print the plan, call nothing
    python register_gateway.py --gateway-id GW # override target gateway

Region: ap-southeast-2 (Sydney).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

# Import the single source of truth for the tool surface.
try:
    from server import TOOL_SPECS  # when run from within mcp-tools/
except ImportError:  # pragma: no cover - allow `python mcp-tools/register_gateway.py`
    from mcp_tools.server import TOOL_SPECS  # type: ignore

REGION = "ap-southeast-2"

# MCP endpoint the gateway target invokes. In production the tools server runs
# behind the AgentCore Gateway's own MCP transport; this env var lets deploy
# override the concrete endpoint without editing code.
MCP_SERVER_ENDPOINT = os.environ.get(
    "MCP_SERVER_ENDPOINT", "mcp://adidlabs-tools"
)


def _gateway_client():  # pragma: no cover - thin boto3 wrapper, stubbed in tests
    """Return the AgentCore control-plane client used to manage gateway targets."""
    import boto3

    return boto3.client("bedrock-agentcore-control", region_name=REGION)


def _resolve_gateway_id(explicit: str | None) -> str:
    """Pick the gateway id from the flag, then env, else a demo default."""
    if explicit:
        return explicit
    gid = os.environ.get("AGENTCORE_GATEWAY_ID")
    if gid:
        return gid
    # Derive nothing risky from the agent ARN; use a stable demo id if unset.
    return os.environ.get("GATEWAY_ID", "adidlabs-tools-gw")


def build_target_payload(gateway_id: str, spec: Dict[str, str]) -> Dict[str, Any]:
    """Build the create_gateway_target request body for one tool."""
    return {
        "gatewayIdentifier": gateway_id,
        "name": spec["name"],
        "description": spec["description"],
        "targetConfiguration": {
            "mcp": {
                "endpoint": MCP_SERVER_ENDPOINT,
                "toolName": spec["name"],
            }
        },
        # Free-form metadata so operators can see which backend each tool hits.
        "tags": {"backend": spec["backend"], "project": "adidlabs"},
    }


def register_all(gateway_id: str, dry_run: bool = False) -> List[Dict[str, Any]]:
    """Register every tool in TOOL_SPECS as a gateway target.

    Returns a list of per-tool result records. On dry-run, no AWS call is made
    and each record is marked ``planned``.
    """
    results: List[Dict[str, Any]] = []
    client = None if dry_run else _gateway_client()

    for spec in TOOL_SPECS:
        payload = build_target_payload(gateway_id, spec)
        if dry_run:
            results.append({"tool": spec["name"], "status": "planned", "payload": payload})
            continue
        try:
            resp = client.create_gateway_target(**payload)
            results.append(
                {
                    "tool": spec["name"],
                    "status": "registered",
                    "targetId": resp.get("targetId") or resp.get("gatewayTargetId"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - report per-tool, keep going
            results.append({"tool": spec["name"], "status": "error", "error": str(exc)})

    return results


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register AdidLaBs MCP tools as gateway targets.")
    parser.add_argument("--gateway-id", default=None, help="AgentCore Gateway identifier")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, call nothing")
    args = parser.parse_args(argv)

    gateway_id = _resolve_gateway_id(args.gateway_id)
    results = register_all(gateway_id, dry_run=args.dry_run)

    print(json.dumps({"gateway_id": gateway_id, "targets": results}, indent=2))
    # Non-zero exit if any real registration errored (dry-run always succeeds).
    failed = [r for r in results if r.get("status") == "error"]
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    sys.exit(main())
