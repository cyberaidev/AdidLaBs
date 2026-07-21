"""The six shopping specialist agents.

Each specialist owns one catalog category (shoes / pants / tshirt / jumper /
jacket / accessory), runs on route ``haiku-4.5``, and answers an A2A
``style_pick`` task from the orchestrator. A specialist:

    1. Pulls candidates from the catalog for its category (deals first) via the
       MCP tools ``get_deals`` / ``get_catalog``.
    2. Grounds its rationale with ``search_lab_knowledge`` (Bedrock KB retrieve);
       if the KB relevance is below the floor it falls back to ``search_web``.
    3. Returns up to N picks + a short rationale + citations in a
       :class:`~agents.common.a2a.TaskResult`.

Personas are short and category-specific. The LLM is optional: if a client is
supplied it writes the rationale; otherwise a deterministic template is used so
the whole mesh runs offline (DEMO_MODE / CI) with no live model calls.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Dual-mode imports: package-relative for tests/tooling (agents.entrypoint), and
# top-level for the AgentCore runtime, which runs this file as /var/task/<name>.py
# with no parent package (direct code deploy zips the agents/ dir contents at root).
try:
    from .common.a2a import TaskEnvelope, TaskResult, ok_result, skipped_result, error_result
    from .common.llm import LLMClient
    from .common.roster import AgentIdentity, category_identities, get_category_identity
    from .common.tools import ToolClient, kb_is_useful
except ImportError:  # pragma: no cover - runtime layout
    from common.a2a import TaskEnvelope, TaskResult, ok_result, skipped_result, error_result
    from common.llm import LLMClient
    from common.roster import AgentIdentity, category_identities, get_category_identity
    from common.tools import ToolClient, kb_is_useful

# Short persona prompt per category (system prompt seed for the rationale LLM).
PERSONAS: dict[str, str] = {
    "shoes": "You are the AdidLaBs SHOES stylist. You pick footwear matched to "
    "the weather - grip and waterproofing for wet days, breathable low-profile "
    "sneakers for warm clear days. Be concrete and brief.",
    "pants": "You are the AdidLaBs PANTS stylist. You match legwear to conditions "
    "- water-resistant or tapered for rain, lightweight for heat. Be brief.",
    "tshirt": "You are the AdidLaBs TSHIRT stylist. You favour breathable tees on "
    "warm sunny days and as a base layer when it's cool. Be brief.",
    "jumper": "You are the AdidLaBs JUMPER stylist. You add midweight warmth for "
    "cool and cold windows and layering. Be brief.",
    "jacket": "You are the AdidLaBs JACKET stylist. You lead on rain and wind - "
    "packable rain shells and windbreakers keep the outfit dry. Be brief.",
    "accessory": "You are the AdidLaBs ACCESSORY stylist. You finish the look with "
    "weather-useful extras - umbrellas and caps for rain, light caps for sun. "
    "Be brief.",
}

_MAX_PICKS = 2


class ShoppingAgent:
    """One category specialist.

    Args:
        category: One of the six catalog categories.
        tools: MCP tool client (Gateway-backed in prod, local in demo/CI).
        llm: Optional LLM client for rationale text.
    """

    def __init__(self, category: str, tools: ToolClient, llm: LLMClient | None = None) -> None:
        if category not in PERSONAS:
            raise ValueError(f"Unknown shopping category: {category!r}")
        self.category = category
        self.identity: AgentIdentity = get_category_identity(category)
        self.tools = tools
        self.llm = llm

    @property
    def persona(self) -> str:
        return PERSONAS[self.category]

    def handle(self, envelope: TaskEnvelope) -> TaskResult:
        """Handle a ``style_pick`` A2A task and return a :class:`TaskResult`."""
        try:
            payload = envelope.payload or {}
            conditions = payload.get("conditions", {})
            user_message = str(payload.get("user_message", ""))

            candidates = self._candidates(user_message, conditions)
            if not candidates:
                return skipped_result(
                    envelope, agent=self.identity.wid, reason=f"No {self.category} in catalog."
                )

            picks = candidates[:_MAX_PICKS]
            citations, grounding = self._ground(conditions, user_message)
            rationale = self._rationale(conditions, picks, grounding)
            return ok_result(
                envelope,
                agent=self.identity.wid,
                picks=picks,
                rationale=rationale,
                citations=citations,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one bad specialist
            return error_result(envelope, agent=self.identity.wid, error=str(exc))

    # -- internals -----------------------------------------------------------
    def _candidates(
        self, user_message: str = "", conditions: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Rank the category pool against the shopper's ask + the conditions.

        The old behaviour returned the same first-N rows every turn. Each
        candidate is now scored: direct keyword hits from the message (name,
        colour, season, usage, article type) weigh most, condition affinity
        (snow/cold -> winter knits and boots, rain -> shells, sun -> summer)
        next, and deals get a small nudge. Ties break on a hash of
        item_id+message so different asks surface different items while the
        same ask stays deterministic.
        """
        deals = self.tools.get_deals(category=self.category, limit=12)
        seen = {d["item_id"] for d in deals if d.get("item_id")}
        catalog = [
            i
            for i in self.tools.get_catalog(category=self.category, limit=24)
            if i.get("item_id") and i["item_id"] not in seen
        ]
        pool = [*deals, *catalog]

        cond = conditions or {}
        dominant = str(cond.get("dominant", "mild"))
        requested = str(cond.get("requested", "") or "")
        tokens = {t for t in (user_message or "").lower().split() if len(t) > 2}

        affinity = {
            "cold": ("winter", "fall", "thermal", "knit", "wool", "fleece",
                     "boot", "crew", "insul", "puffer", "warm"),
            "rain": ("rain", "shell", "waterproof", "storm", "wind", "boot", "cap"),
            "sun": ("summer", "spring", "breath", "mesh", "tee", "light", "cap"),
        }
        snow_words = ("winter", "thermal", "boot", "wool", "fleece", "knit", "insul")

        def searchable(item: dict[str, Any]) -> str:
            return " ".join(
                str(item.get(k, "")) for k in (
                    "title", "name", "base_colour", "colour", "season",
                    "usage", "article_type", "gender",
                )
            ).lower()

        def score(item: dict[str, Any]) -> tuple[float, int]:
            text = searchable(item)
            points = 0.0
            for tok in tokens:
                if tok in text:
                    points += 3.0
            for hint in affinity.get(dominant, ()):
                if hint in text:
                    points += 1.5
            if requested == "snow":
                points += sum(1.0 for w in snow_words if w in text)
            if int(item.get("deal_pct", item.get("discount_pct", 0)) or 0) > 0:
                points += 0.5
            tiebreak = int(
                hashlib.md5(
                    f"{item.get('item_id','')}::{user_message}".encode()
                ).hexdigest()[:8],
                16,
            )
            return (points, tiebreak)

        return sorted(pool, key=score, reverse=True)

    def _ground(
        self, conditions: dict[str, Any], user_message: str
    ) -> tuple[list[dict[str, Any]], str]:
        """Retrieve KB passages; fall back to web only on a KB miss.

        Returns ``(citations, grounding_text)``. Citations carry ``source`` +
        ``score`` for KB hits, or ``url`` for web hits.
        """
        query = self._kb_query(conditions, user_message)
        passages = self.tools.search_lab_knowledge(query, top_k=3)
        if kb_is_useful(passages):
            citations = [
                {"source": p.get("source"), "score": p.get("score")} for p in passages
            ]
            grounding = " ".join(p.get("text", "") for p in passages)
            return citations, grounding
        # KB miss -> web fallback.
        hits = self.tools.search_web(query, max_results=2)
        citations = [{"url": h.get("url"), "title": h.get("title")} for h in hits]
        grounding = " ".join(h.get("snippet", "") for h in hits)
        return citations, grounding

    def _kb_query(self, conditions: dict[str, Any], user_message: str) -> str:
        dominant = conditions.get("dominant", "mild")
        return f"{dominant} weather {self.category} outfit {user_message}".strip()

    def _rationale(
        self, conditions: dict[str, Any], picks: list[dict[str, Any]], grounding: str
    ) -> str:
        titles = ", ".join(p.get("title", p.get("item_id", "item")) for p in picks)
        dominant = conditions.get("dominant", "mild")
        if self.llm is None:
            return (
                f"For {dominant} conditions, {self.category}: {titles}. "
                f"{grounding}".strip()
            )
        try:
            content = self.llm.chat(
                self.identity.route,
                [
                    {"role": "system", "content": self.persona},
                    {
                        "role": "user",
                        "content": (
                            f"Shopper asked: {conditions.get('requested') or 'weather-matched picks'}. "
                            f"Conditions: {dominant}. Candidate {self.category}: "
                            f"{titles}. Grounding: {grounding}. Write one sentence "
                            f"(<=25 words) answering the ask with these picks."
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=80,
            ).strip()
            return content or f"{self.category}: {titles} for {dominant} weather."
        except Exception as exc:  # noqa: BLE001 - deterministic fallback
            print(f"[llm] {self.identity.wid} rationale fallback: {exc}", flush=True)
            return f"{self.category}: {titles} for {dominant} weather."


def build_shopping_agents(
    tools: ToolClient, llm: LLMClient | None = None
) -> dict[str, ShoppingAgent]:
    """Instantiate all six specialists keyed by category (roster order)."""
    return {
        ident.category: ShoppingAgent(ident.category, tools, llm)  # type: ignore[arg-type]
        for ident in category_identities()
    }
