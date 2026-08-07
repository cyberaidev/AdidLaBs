"""GET /api/trace - per-session OpenTelemetry component breakdown.

The AgentCore runtime runs with ADOT observability enabled; the mesh emits a
span per component (weather agent, each shopping agent, orchestrator compose,
every LiteLLM call) and AgentCore tags everything with the runtime session id.
With CloudWatch Transaction Search enabled those spans land in the ``aws/spans``
log group, which this route queries via Logs Insights.

The session id is derived from the caller's JWT exactly like chat.py does
(the Cognito ``sub`` IS the runtimeSessionId), so the storefront simply calls
GET /api/trace and receives its own session's breakdown:

    {"session": ..., "window_minutes": 60, "spans_scanned": 42,
     "components": [{"component": "SHOES", "name": "agent.shoes",
                     "calls": 3, "total_ms": 812.4, "avg_ms": 270.8}, ...]}

Data source: the mesh emits one ``[otel-span] {json}`` log line per component
span (see agents/common/otel.py) — CloudWatch log delivery is synchronous
with the invocation, unlike in-process OTLP export, which AgentCore's
microVM freeze can drop. The real OTEL spans still flow to GenAI
Observability / X-Ray for the AWS-side view.

JWT-protected like /api/terminal. Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import defaultdict
from typing import Any

import boto3

try:  # package-relative (tests) with zip-root fallback (Lambda)
    from common.http import error, get_method, get_query, get_user_id, preflight, respond
    from terminal import _runtime_log_group
except ImportError:  # pragma: no cover
    from backend.common.http import (
        error, get_method, get_query, get_user_id, preflight, respond,
    )
    from backend.terminal import _runtime_log_group

_SPAN_MARK = "[otel-span]"
_MIN_SESSION_ID_LEN = 33
_DEFAULT_MINUTES = 60
_MAX_MINUTES = 720


def _session_id(user_id: str) -> str:
    """Mirror chat.py: the >=33-char runtimeSessionId for this user."""
    if len(user_id) >= _MIN_SESSION_ID_LEN:
        return user_id
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"{user_id}-{digest}"[:64]


def handler(event, context):  # noqa: ANN001 - Lambda signature
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "GET":
        return error(405, "GET only")

    user_id = get_user_id(event)
    if not user_id:
        return error(401, "authentication required")
    session = _session_id(user_id)

    try:
        minutes = min(int(get_query(event).get("minutes", _DEFAULT_MINUTES)),
                      _MAX_MINUTES)
    except ValueError:
        return error(400, "minutes must be an integer")

    logs = boto3.client(
        "logs", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")
    )
    group = _runtime_log_group(logs)
    if not group:
        return respond(200, {
            "session": session, "window_minutes": minutes, "spans_scanned": 0,
            "components": [],
            "note": "runtime log group not found yet.",
        })

    # Two quoted terms = AND in a CloudWatch filter pattern: only this
    # session's span lines come back.
    start = int((time.time() - minutes * 60) * 1000)
    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "total_ms": 0.0, "name": ""}
    )
    scanned = 0
    token: str | None = None
    for _ in range(5):
        kwargs: dict[str, Any] = {
            "logGroupName": group,
            "startTime": start,
            "filterPattern": f'"{_SPAN_MARK}" "{session}"',
            "limit": 1000,
        }
        if token:
            kwargs["nextToken"] = token
        resp = logs.filter_log_events(**kwargs)
        for ev in resp.get("events", []):
            message = str(ev.get("message", ""))
            mark = message.find(_SPAN_MARK)
            if mark < 0:
                continue
            try:
                record = json.loads(message[mark + len(_SPAN_MARK):].strip())
            except (TypeError, ValueError):
                continue
            if record.get("session") != session:
                continue
            scanned += 1
            component = str(record.get("component") or "?")
            bucket = agg[component]
            bucket["calls"] += 1
            bucket["total_ms"] += float(record.get("ms") or 0.0)
            bucket["name"] = str(record.get("name") or "")
        token = resp.get("nextToken")
        if not token:
            break

    components = [
        {
            "component": comp,
            "name": data["name"],
            "calls": data["calls"],
            "total_ms": round(data["total_ms"], 1),
            "avg_ms": round(data["total_ms"] / data["calls"], 1),
        }
        for comp, data in agg.items()
        if data["calls"]
    ]
    components.sort(key=lambda c: c["total_ms"], reverse=True)

    return respond(200, {
        "session": session,
        "window_minutes": minutes,
        "spans_scanned": scanned,
        "components": components,
    })
