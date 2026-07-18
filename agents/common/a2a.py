"""A2A (agent-to-agent) task envelope helpers.

The orchestrator fans out to the six category specialists using a small,
explicit *task envelope* rather than ad-hoc dict passing. The envelope carries:

    * ``task_id``   - correlation id for a single fan-out request
    * ``sender``    - workload identity of the sender (e.g. orchestrator wid)
    * ``recipient`` - workload identity of the target agent
    * ``intent``    - what is being asked (``"style_pick"`` today)
    * ``payload``   - the request body (user message + weather conditions + hints)

Replies come back as a :class:`TaskResult` carrying the same ``task_id`` plus a
``status`` and the agent's ``picks`` / ``rationale`` / ``citations``.

**Transport note (cost tradeoff, see agents/README.md):** in this demo the
envelopes are delivered *in-process* - the orchestrator calls the specialist's
handler directly inside the one AgentCore runtime. The envelope shape is
deliberately transport-agnostic (pure JSON-serialisable dataclasses) so the very
same messages could be posted to a remote AgentCore runtime per agent without
changing any agent logic. We keep it in-process to avoid N idle runtimes.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# Supported intents. One today; kept as constants so routing stays explicit.
INTENT_STYLE_PICK = "style_pick"

STATUS_OK = "ok"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"


@dataclass
class TaskEnvelope:
    """A single agent-to-agent request.

    Attributes:
        recipient: Workload identity id of the target agent (``adidlabs/...``).
        sender: Workload identity id of the sender.
        intent: One of the ``INTENT_*`` constants.
        payload: Arbitrary JSON-serialisable request body.
        task_id: Correlation id; auto-generated if omitted.
    """

    recipient: str
    sender: str
    intent: str
    payload: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict (ready for a remote transport)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskEnvelope":
        """Rebuild an envelope from a transport payload."""
        return cls(
            recipient=data["recipient"],
            sender=data["sender"],
            intent=data["intent"],
            payload=dict(data.get("payload", {})),
            task_id=data.get("task_id") or uuid.uuid4().hex,
        )


@dataclass
class TaskResult:
    """An agent-to-agent reply, correlated by ``task_id``.

    Attributes:
        task_id: Correlation id copied from the originating envelope.
        agent: Workload identity id of the responding agent.
        status: One of ``STATUS_OK`` / ``STATUS_SKIPPED`` / ``STATUS_ERROR``.
        picks: Zero or more product picks (catalog item dicts, enriched).
        rationale: Short human-readable justification for the picks.
        citations: KB source citations backing the rationale (may be empty).
        error: Populated only when ``status == STATUS_ERROR``.
    """

    task_id: str
    agent: str
    status: str = STATUS_OK
    picks: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskResult":
        """Rebuild a result from a transport payload."""
        return cls(
            task_id=data["task_id"],
            agent=data["agent"],
            status=data.get("status", STATUS_OK),
            picks=list(data.get("picks", [])),
            rationale=data.get("rationale", ""),
            citations=list(data.get("citations", [])),
            error=data.get("error"),
        )


def make_task(
    *, sender: str, recipient: str, payload: dict[str, Any], intent: str = INTENT_STYLE_PICK
) -> TaskEnvelope:
    """Convenience constructor for a style-pick task envelope."""
    return TaskEnvelope(
        recipient=recipient, sender=sender, intent=intent, payload=dict(payload)
    )


def ok_result(
    envelope: TaskEnvelope,
    *,
    agent: str,
    picks: list[dict[str, Any]],
    rationale: str,
    citations: list[dict[str, Any]] | None = None,
) -> TaskResult:
    """Build a successful result correlated to ``envelope``."""
    return TaskResult(
        task_id=envelope.task_id,
        agent=agent,
        status=STATUS_OK,
        picks=list(picks),
        rationale=rationale,
        citations=list(citations or []),
    )


def skipped_result(envelope: TaskEnvelope, *, agent: str, reason: str) -> TaskResult:
    """Build a 'not relevant for this forecast' result."""
    return TaskResult(
        task_id=envelope.task_id, agent=agent, status=STATUS_SKIPPED, rationale=reason
    )


def error_result(envelope: TaskEnvelope, *, agent: str, error: str) -> TaskResult:
    """Build an error result so one bad specialist never sinks the fan-out."""
    return TaskResult(
        task_id=envelope.task_id, agent=agent, status=STATUS_ERROR, error=error
    )
