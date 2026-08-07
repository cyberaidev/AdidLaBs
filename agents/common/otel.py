"""OpenTelemetry helper for the agent mesh — safe no-op without the SDK.

Two delivery paths for the same instrumentation points:

* Real OTEL spans (when the runtime is launched with observability): nested
  under the AgentCore request span, visible in CloudWatch GenAI Observability
  / X-Ray. NOTE: AgentCore freezes the microVM the moment a response returns,
  so in-process span export is best-effort even with a force-flush — only
  the platform's root span is guaranteed.
* A structured ``[otel-span] {json}`` stdout line per span — CloudWatch log
  delivery is synchronous with the invocation, so this path is reliable. The
  storefront's /api/trace builds its per-session component breakdown from
  these lines; durations are measured by the span itself.

Locally / in tests the OTEL import fails and only the log line remains.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

# The runtimeSessionId for the current invocation (== the Cognito sub for
# real users). Stamped on every span/log line so /api/trace can filter.
_SESSION: ContextVar[str] = ContextVar("adidlabs_session", default="")


def set_session(session_id: str) -> None:
    """Record the current invocation's session id (call from the entrypoint)."""
    _SESSION.set(str(session_id or ""))


def _emit(name: str, ms: float, attributes: dict[str, Any]) -> None:
    record = {
        "name": name,
        "component": str(attributes.get("component") or name.split(".")[-1].upper()),
        "session": _SESSION.get(),
        "ms": round(ms, 2),
    }
    print(f"[otel-span] {json.dumps(record)}", flush=True)


try:  # pragma: no cover - depends on runtime install
    from opentelemetry import trace as _trace

    _TRACER = _trace.get_tracer("adidlabs.mesh")

    @contextmanager
    def component_span(name: str, **attributes: Any) -> Iterator[None]:
        """Span around one mesh component (agent node / A2A call / LLM call)."""
        started = time.perf_counter()
        try:
            with _TRACER.start_as_current_span(name) as span:
                session = _SESSION.get()
                if session:
                    span.set_attribute("session.id", session)
                for key, value in attributes.items():
                    if value is not None:
                        span.set_attribute(f"adidlabs.{key}", str(value))
                yield
        finally:
            _emit(name, (time.perf_counter() - started) * 1000, attributes)

    def flush_spans(timeout_millis: int = 3000) -> None:
        """Force-flush buffered spans before AgentCore freezes the microVM."""
        provider = _trace.get_tracer_provider()
        force_flush = getattr(provider, "force_flush", None)
        if callable(force_flush):
            try:
                force_flush(timeout_millis)
            except Exception:  # noqa: BLE001 - never fail a reply over telemetry
                pass

except ImportError:  # pragma: no cover - local/test path

    @contextmanager
    def component_span(name: str, **attributes: Any) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            _emit(name, (time.perf_counter() - started) * 1000, attributes)

    def flush_spans(timeout_millis: int = 3000) -> None:  # noqa: ARG001
        pass
