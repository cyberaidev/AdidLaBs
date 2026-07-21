"""GET /api/telemetry - LiteLLM gateway model usage for the storefront.

Every model call in AdidLaBs flows through the LiteLLM gateway to Bedrock, and
Bedrock emits per-model CloudWatch metrics automatically (namespace
``AWS/Bedrock``: Invocations, InputTokenCount, OutputTokenCount,
InvocationLatency). This handler aggregates them so the storefront's LiteLLM
panel can show incremental token usage and latency per route — no LiteLLM
database, no extra cost.

Query params:
  * ``hours``  lookback window (default 24, max 168).

Public like GET /api/agents — aggregate demo telemetry, no user data.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import boto3

from common.http import error, get_method, get_query, preflight, respond

_DEFAULT_HOURS = 24
_MAX_HOURS = 168
_PERIOD_S = 3600

# Contract LiteLLM routes; anything else that shows up (e.g. Titan embeddings
# from Knowledge Base ingestion/retrieval) is still reported, labelled by kind.
_ROUTE_HINTS = (
    ("nova-pro", "nova-pro"),
    ("haiku", "haiku-4.5"),
    ("titan-embed", "titan-embed (KB)"),
)


def _cloudwatch():
    return boto3.client(
        "cloudwatch", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")
    )


def _route_for(model_id: str) -> str:
    lowered = model_id.lower()
    for hint, route in _ROUTE_HINTS:
        if hint in lowered:
            return route
    return "other"


def _model_ids(cw) -> list[str]:
    """Every ModelId that emitted Bedrock invocation metrics in this region."""
    ids: set[str] = set()
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "Namespace": "AWS/Bedrock",
            "MetricName": "Invocations",
        }
        if token:
            kwargs["NextToken"] = token
        resp = cw.list_metrics(**kwargs)
        for metric in resp.get("Metrics", []):
            for dim in metric.get("Dimensions", []):
                if dim.get("Name") == "ModelId":
                    ids.add(dim["Value"])
        token = resp.get("NextToken")
        if not token:
            break
    return sorted(ids)


def _stat(cw, metric: str, model_id: str, start: datetime, end: datetime,
          stat: str) -> float:
    resp = cw.get_metric_statistics(
        Namespace="AWS/Bedrock",
        MetricName=metric,
        Dimensions=[{"Name": "ModelId", "Value": model_id}],
        StartTime=start,
        EndTime=end,
        Period=_PERIOD_S,
        Statistics=[stat],
    )
    points = resp.get("Datapoints", [])
    if not points:
        return 0.0
    if stat == "Sum":
        return float(sum(p.get("Sum", 0.0) for p in points))
    return float(sum(p.get("Average", 0.0) for p in points) / len(points))


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for GET /api/telemetry."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "GET":
        return error(405, "method not allowed")

    try:
        hours = min(int(get_query(event).get("hours", _DEFAULT_HOURS)), _MAX_HOURS)
    except ValueError:
        return error(400, "hours must be an integer")
    if hours < 1:
        return error(400, "hours must be positive")

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    cw = _cloudwatch()
    models: list[dict[str, Any]] = []
    totals = {"invocations": 0, "tokens_in": 0, "tokens_out": 0}

    for model_id in _model_ids(cw):
        invocations = int(_stat(cw, "Invocations", model_id, start, end, "Sum"))
        tokens_in = int(_stat(cw, "InputTokenCount", model_id, start, end, "Sum"))
        tokens_out = int(_stat(cw, "OutputTokenCount", model_id, start, end, "Sum"))
        latency = round(_stat(cw, "InvocationLatency", model_id, start, end, "Average"))
        if not any((invocations, tokens_in, tokens_out)):
            continue
        models.append({
            "model_id": model_id,
            "route": _route_for(model_id),
            "invocations": invocations,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "avg_latency_ms": latency,
        })
        totals["invocations"] += invocations
        totals["tokens_in"] += tokens_in
        totals["tokens_out"] += tokens_out

    models.sort(key=lambda m: m["tokens_in"] + m["tokens_out"], reverse=True)
    return respond(200, {
        "window_hours": hours,
        "region": os.environ.get("AWS_REGION", "ap-southeast-2"),
        "gateway": "litellm",
        "models": models,
        "totals": {
            **totals,
            "tokens": totals["tokens_in"] + totals["tokens_out"],
        },
    })
