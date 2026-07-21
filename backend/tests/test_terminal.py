"""Tests for GET /api/terminal (AgentCore runtime session lines).

Concept demo - no affiliation with adidas AG. All products fictional.
No real CloudWatch calls - the logs client is stubbed.
"""

from __future__ import annotations

import json

import terminal


class FakeLogs:
    def __init__(self, groups=None, events=None):
        self._groups = groups or []
        self._events = events or []

    def describe_log_groups(self, **kwargs):
        prefix = kwargs.get("logGroupNamePrefix", "")
        return {
            "logGroups": [g for g in self._groups if g["logGroupName"].startswith(prefix)]
        }

    def filter_log_events(self, **kwargs):
        return {"events": self._events}


def _get(query=None):
    return {
        "requestContext": {"http": {"method": "GET"}},
        "queryStringParameters": query or {},
    }


def test_matches_full_wid_and_short_suffix():
    assert terminal._matches("[a2a] adidlabs/shoes-4e2a -> x", "adidlabs/shoes-4e2a")
    assert terminal._matches("picked by shoes-4e2a", "adidlabs/shoes-4e2a")
    assert not terminal._matches("[a2a] adidlabs/pants-8c1d", "adidlabs/shoes-4e2a")
    assert terminal._matches("anything", "")


def test_runtime_log_group_picks_newest(monkeypatch):
    logs = FakeLogs(groups=[
        {"logGroupName": terminal._LOG_PREFIX + "adidlabs_agents-OLD-DEFAULT",
         "creationTime": 100},
        {"logGroupName": terminal._LOG_PREFIX + "adidlabs_agents-NEW-DEFAULT",
         "creationTime": 200},
    ])
    assert terminal._runtime_log_group(logs).endswith("NEW-DEFAULT")


def test_handler_returns_filtered_events(monkeypatch):
    logs = FakeLogs(
        groups=[{"logGroupName": terminal._LOG_PREFIX + "adidlabs_agents-X-DEFAULT",
                 "creationTime": 1}],
        events=[
            {"timestamp": 2, "logStreamName": "s", "message": "[a2a] adidlabs/shoes-4e2a ok"},
            {"timestamp": 1, "logStreamName": "s", "message": "[a2a] adidlabs/pants-8c1d ok"},
        ],
    )
    monkeypatch.setattr(terminal, "_logs_client", lambda: logs)
    resp = terminal.handler(_get({"wid": "adidlabs/shoes-4e2a"}))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["count"] == 1
    assert "shoes-4e2a" in body["events"][0]["message"]


def test_handler_no_group_note(monkeypatch):
    monkeypatch.setattr(terminal, "_logs_client", lambda: FakeLogs())
    resp = terminal.handler(_get())
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["log_group"] is None
    assert body["events"] == []


def test_handler_rejects_bad_params(monkeypatch):
    monkeypatch.setattr(terminal, "_logs_client", lambda: FakeLogs())
    assert terminal.handler(_get({"limit": "nope"}))["statusCode"] == 400
    assert terminal.handler(_get({"limit": "0"}))["statusCode"] == 400
