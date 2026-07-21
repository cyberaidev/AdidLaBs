"""GET /api/terminal - read recent AgentCore runtime session lines.

Powers the storefront's per-agent web terminal (AgentsPanel -> terminal
drawer): returns recent events from the AgentCore runtime's CloudWatch log
group so a session's orchestration can be read live from the browser.

Behaviour:
  * The runtime log group is discovered by prefix
    (``/aws/bedrock-agentcore/runtimes/<hint>``) picking the newest match, so
    runtime re-creations (new ``-XXXX`` suffixes) keep working with no
    configuration change. Override the hint with ``AGENT_RUNTIME_LOG_HINT``.
  * ``?wid=adidlabs/shoes-4e2a`` filters lines to one agent: a line matches
    when it contains the wid (or its short suffix, e.g. ``shoes-4e2a``).
  * ``?limit=`` caps returned events (default 200, max 500);
    ``?minutes=`` bounds the lookback window (default 60, max 1440).

JWT-protected like /api/bag — session logs are for signed-in lab members.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import os
import time
from typing import Any, Mapping

import boto3

from common.http import error, get_method, get_query, preflight, respond

_LOG_PREFIX = "/aws/bedrock-agentcore/runtimes/"
_DEFAULT_HINT = "adidlabs_agents"
_DEFAULT_LIMIT = 200
_MAX_LIMIT = 500
_DEFAULT_MINUTES = 60
_MAX_MINUTES = 1440


def _logs_client():
    return boto3.client(
        "logs", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")
    )


def _runtime_log_group(logs) -> str | None:
    """Newest runtime log group whose name starts with the configured hint."""
    hint = os.environ.get("AGENT_RUNTIME_LOG_HINT", _DEFAULT_HINT)
    prefix = _LOG_PREFIX + hint
    groups: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"logGroupNamePrefix": prefix}
        if token:
            kwargs["nextToken"] = token
        resp = logs.describe_log_groups(**kwargs)
        groups.extend(resp.get("logGroups", []))
        token = resp.get("nextToken")
        if not token:
            break
    if not groups:
        return None
    groups.sort(key=lambda g: g.get("creationTime", 0), reverse=True)
    return groups[0]["logGroupName"]


def _matches(message: str, wid: str) -> bool:
    if not wid:
        return True
    if wid in message:
        return True
    short = wid.rsplit("/", 1)[-1]
    return bool(short) and short in message


def _fetch_events(logs, group: str, minutes: int, limit: int,
                  wid: str) -> list[dict[str, Any]]:
    start = int((time.time() - minutes * 60) * 1000)
    events: list[dict[str, Any]] = []
    token: str | None = None
    # Read up to a few pages; keep only the newest `limit` matching lines.
    for _ in range(5):
        kwargs: dict[str, Any] = {
            "logGroupName": group,
            "startTime": start,
            "limit": _MAX_LIMIT,
        }
        if token:
            kwargs["nextToken"] = token
        resp = logs.filter_log_events(**kwargs)
        for ev in resp.get("events", []):
            message = str(ev.get("message", "")).rstrip("\n")
            if _matches(message, wid):
                events.append(
                    {
                        "ts": ev.get("timestamp"),
                        "stream": str(ev.get("logStreamName", ""))[-24:],
                        "message": message[:2000],
                    }
                )
        token = resp.get("nextToken")
        if not token:
            break
    events.sort(key=lambda e: e.get("ts") or 0)
    return events[-limit:]


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for GET /api/terminal."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "GET":
        return error(405, "method not allowed")

    query = get_query(event)
    wid = (query.get("wid") or "").strip()
    try:
        limit = min(int(query.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)
        minutes = min(int(query.get("minutes", _DEFAULT_MINUTES)), _MAX_MINUTES)
    except ValueError:
        return error(400, "limit and minutes must be integers")
    if limit < 1 or minutes < 1:
        return error(400, "limit and minutes must be positive")

    logs = _logs_client()
    group = _runtime_log_group(logs)
    if not group:
        return respond(200, {
            "log_group": None,
            "wid": wid or None,
            "events": [],
            "note": "No AgentCore runtime log group found yet — deploy the "
                    "agents and send a chat message to start a session.",
        })

    events = _fetch_events(logs, group, minutes, limit, wid)
    return respond(200, {
        "log_group": group,
        "wid": wid or None,
        "minutes": minutes,
        "count": len(events),
        "events": events,
    })
