"""Tests for GET /api/telemetry (LiteLLM/Bedrock usage panel).

Concept demo - no affiliation with adidas AG. All products fictional.
No real CloudWatch calls - the client is stubbed.
"""

from __future__ import annotations

import json

import telemetry


class FakeCloudWatch:
    def __init__(self, model_ids=None, sums=None, avg=120.0):
        self._model_ids = model_ids or []
        self._sums = sums or {}
        self._avg = avg

    def list_metrics(self, **kwargs):
        return {
            "Metrics": [
                {"Dimensions": [{"Name": "ModelId", "Value": mid}]}
                for mid in self._model_ids
            ]
        }

    def get_metric_statistics(self, **kwargs):
        metric = kwargs["MetricName"]
        stat = kwargs["Statistics"][0]
        if stat == "Average":
            return {"Datapoints": [{"Average": self._avg}]}
        value = self._sums.get(metric, 0)
        return {"Datapoints": [{"Sum": value}]} if value else {"Datapoints": []}


def _get(query=None):
    return {
        "requestContext": {"http": {"method": "GET"}},
        "queryStringParameters": query or {},
    }


def test_route_mapping():
    assert telemetry._route_for("apac.amazon.nova-pro-v1:0") == "nova-pro"
    assert telemetry._route_for("au.anthropic.claude-haiku-4-5-20251001-v1:0") == "haiku-4.5"
    assert telemetry._route_for("amazon.titan-embed-text-v2:0") == "titan-embed (KB)"
    assert telemetry._route_for("something-else") == "other"


def test_handler_aggregates_totals(monkeypatch):
    fake = FakeCloudWatch(
        model_ids=["apac.amazon.nova-pro-v1:0", "au.anthropic.claude-haiku-4-5-20251001-v1:0"],
        sums={"Invocations": 4, "InputTokenCount": 1000, "OutputTokenCount": 250},
    )
    monkeypatch.setattr(telemetry, "_cloudwatch", lambda: fake)
    resp = telemetry.handler(_get())
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert len(body["models"]) == 2
    assert body["models"][0]["route"] in ("nova-pro", "haiku-4.5")
    assert body["totals"]["invocations"] == 8
    assert body["totals"]["tokens"] == 2 * (1000 + 250)


def test_handler_skips_idle_models(monkeypatch):
    fake = FakeCloudWatch(model_ids=["apac.amazon.nova-pro-v1:0"], sums={})
    monkeypatch.setattr(telemetry, "_cloudwatch", lambda: fake)
    body = json.loads(telemetry.handler(_get())["body"])
    assert body["models"] == []
    assert body["totals"]["tokens"] == 0


def test_handler_rejects_bad_hours(monkeypatch):
    monkeypatch.setattr(telemetry, "_cloudwatch", lambda: FakeCloudWatch())
    assert telemetry.handler(_get({"hours": "x"}))["statusCode"] == 400
    assert telemetry.handler(_get({"hours": "0"}))["statusCode"] == 400
