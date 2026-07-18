"""Tests for search_lab_knowledge and search_web.

Concept demo - no affiliation with adidas AG. All products fictional.

Covers the three contract paths:
  1. KB-available (high score => relevant=True, source="kb")
  2. KB-available but low score (score-gating => relevant=False)
  3. KB-degraded-to-web (KB unset / retrieve raises => web fallback)

Plus the search_web providers (ddgs default, Tavily when keyed). No real
Bedrock, ddgs, or Tavily traffic - everything is stubbed.
"""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# Fake Bedrock Agent Runtime client for KB retrieve.
# --------------------------------------------------------------------------- #

class FakeKBClient:
    def __init__(self, results, raises=None):
        self._results = results
        self._raises = raises
        self.calls = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return {"retrievalResults": self._results}


def _kb_hit(text, score, uri="s3://adidlabs-kb/doc.md"):
    return {
        "content": {"text": text},
        "score": score,
        "location": {"s3Location": {"uri": uri}},
    }


@pytest.fixture
def server(monkeypatch):
    import server as srv
    # Ensure no Tavily by default; individual tests opt in.
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    return srv


# --------------------------------------------------------------------------- #
# 1. KB-available path (strong score => grounded).
# --------------------------------------------------------------------------- #

def test_kb_available_high_score_is_relevant(server, monkeypatch):
    monkeypatch.setenv("KB_ID", "kb-abc123")
    fake = FakeKBClient(
        [
            _kb_hit("Drizzle Shell uses a 3-layer waterproof membrane.", 0.82),
            _kb_hit("Care: cold wash, no tumble dry.", 0.55),
        ]
    )
    monkeypatch.setattr(server, "_bedrock_agent_runtime_client", lambda: fake)

    result = server.search_lab_knowledge_impl("waterproof jacket fabric", top_k=3)

    assert result["source"] == "kb"
    assert result["degraded"] is False
    assert result["count"] == 2
    assert result["top_score"] == 0.82
    assert result["relevant"] is True  # 0.82 >= threshold
    # Sorted best-first with clean chunk shape.
    assert result["results"][0]["score"] == 0.82
    assert result["results"][0]["source_uri"].startswith("s3://")
    # The KB was actually queried with the right id.
    assert fake.calls[0]["knowledgeBaseId"] == "kb-abc123"


# --------------------------------------------------------------------------- #
# 2. Score-gating: KB responds but the top hit is weak => relevant=False.
# --------------------------------------------------------------------------- #

def test_kb_low_score_gates_to_not_relevant(server, monkeypatch):
    monkeypatch.setenv("KB_ID", "kb-abc123")
    fake = FakeKBClient([_kb_hit("loosely related passage", 0.12)])
    monkeypatch.setattr(server, "_bedrock_agent_runtime_client", lambda: fake)

    result = server.search_lab_knowledge_impl("something obscure", top_k=3)

    assert result["source"] == "kb"
    assert result["degraded"] is False
    assert result["count"] == 1
    assert result["top_score"] == 0.12
    # Below KB_RELEVANCE_THRESHOLD => orchestrator should go to web.
    assert result["relevant"] is False
    assert result["threshold"] == server.KB_RELEVANCE_THRESHOLD


def test_kb_empty_results_not_relevant(server, monkeypatch):
    monkeypatch.setenv("KB_ID", "kb-abc123")
    fake = FakeKBClient([])
    monkeypatch.setattr(server, "_bedrock_agent_runtime_client", lambda: fake)

    result = server.search_lab_knowledge_impl("no hits", top_k=3)
    assert result["count"] == 0
    assert result["top_score"] == 0.0
    assert result["relevant"] is False


# --------------------------------------------------------------------------- #
# 3. KB-degraded-to-web path.
# --------------------------------------------------------------------------- #

def test_kb_missing_id_degrades_to_web(server, monkeypatch):
    monkeypatch.delenv("KB_ID", raising=False)

    # Stub the web layer so no real ddgs/Tavily traffic occurs.
    monkeypatch.setattr(
        server,
        "search_web_impl",
        lambda query, max_results=5: {
            "source": "web",
            "provider": "ddgs",
            "web_sourced": True,
            "query": query,
            "count": 1,
            "results": [
                {"title": "T", "url": "https://ex.com", "snippet": "web snippet", "web_sourced": True}
            ],
        },
    )

    result = server.search_lab_knowledge_impl("anything", top_k=2)

    assert result["source"] == "web"
    assert result["degraded"] is True
    assert "KB_ID not configured" in result["degrade_reason"]
    assert result["relevant"] is False  # web is never authoritative brand knowledge
    # Same envelope keys as the KB path so agents need no signature change.
    for key in ("source", "query", "count", "top_score", "threshold", "relevant", "results"):
        assert key in result
    assert result["results"][0]["text"] == "web snippet"
    assert result["results"][0]["source_uri"] == "https://ex.com"


def test_kb_retrieve_exception_degrades_to_web(server, monkeypatch):
    monkeypatch.setenv("KB_ID", "kb-abc123")
    fake = FakeKBClient([], raises=RuntimeError("S3 Vectors preview unavailable"))
    monkeypatch.setattr(server, "_bedrock_agent_runtime_client", lambda: fake)
    monkeypatch.setattr(
        server,
        "search_web_impl",
        lambda query, max_results=5: {
            "source": "web",
            "provider": "ddgs",
            "web_sourced": True,
            "query": query,
            "count": 0,
            "results": [],
        },
    )

    result = server.search_lab_knowledge_impl("boom", top_k=3)
    assert result["degraded"] is True
    assert "KB retrieve failed" in result["degrade_reason"]
    assert result["relevant"] is False


# --------------------------------------------------------------------------- #
# search_web providers.
# --------------------------------------------------------------------------- #

def test_search_web_uses_ddgs_by_default(server, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    captured = {}

    def fake_ddgs(query, max_results):
        captured["query"] = query
        return {
            "source": "web",
            "provider": "ddgs",
            "web_sourced": True,
            "query": query,
            "count": 1,
            "results": [{"title": "x", "url": "https://d.com", "snippet": "s", "web_sourced": True}],
        }

    monkeypatch.setattr(server, "_search_web_ddgs", fake_ddgs)
    # Guard: Tavily backend must not be called.
    monkeypatch.setattr(
        server,
        "_search_web_tavily",
        lambda *a, **k: pytest.fail("Tavily called without key"),
    )

    result = server.search_web_impl("rainy day shoes")
    assert result["provider"] == "ddgs"
    assert result["web_sourced"] is True
    assert all(r["web_sourced"] for r in result["results"])
    assert captured["query"] == "rainy day shoes"


def test_search_web_uses_tavily_when_keyed(server, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")

    def fake_tavily(query, max_results, api_key):
        assert api_key == "tvly-secret"
        return {
            "source": "web",
            "provider": "tavily",
            "web_sourced": True,
            "query": query,
            "count": 1,
            "results": [{"title": "t", "url": "https://t.com", "snippet": "c", "score": 0.9, "web_sourced": True}],
        }

    monkeypatch.setattr(server, "_search_web_tavily", fake_tavily)
    monkeypatch.setattr(
        server,
        "_search_web_ddgs",
        lambda *a, **k: pytest.fail("ddgs called while Tavily keyed"),
    )

    result = server.search_web_impl("waterproof jacket")
    assert result["provider"] == "tavily"
    assert result["web_sourced"] is True


def test_ddgs_backend_marks_results_and_handles_missing_lib(server, monkeypatch):
    """When the ddgs package can't be imported, tool degrades to empty, not crash."""
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "ddgs":
            raise ImportError("ddgs not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    result = server._search_web_ddgs("query", 3)
    assert result["provider"] == "ddgs"
    assert result["web_sourced"] is True
    assert result["count"] == 0
    assert "ddgs unavailable" in result["error"]
