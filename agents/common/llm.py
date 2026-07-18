"""OpenAI-compatible LLM client for the AdidLaBs agent mesh.

Every model call in AdidLaBs goes through the LiteLLM gateway, which is reached
over an OpenAI-compatible ``/chat/completions`` surface at ``LITELLM_URL``.
Application code NEVER names a raw Bedrock model id - it names one of two
LiteLLM *routes* instead:

    * ``nova-pro``   -> bedrock/apac.amazon.nova-pro-v1:0          (orchestrator)
    * ``haiku-4.5``  -> bedrock/apac.anthropic.claude-haiku-4-5... (all others)

The route -> model mapping lives inside LiteLLM's config, so a model swap is a
one-line change there and no agent code moves. This module only knows route
*names*; it validates them against ``ALLOWED_ROUTES`` so a typo fails loudly
instead of silently hitting the wrong model.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# The two named LiteLLM routes. These are the ONLY strings agents may pass as a
# model. They are route names, not Bedrock model ids - LiteLLM resolves them to
# the APAC cross-region inference profiles.
ROUTE_NOVA_PRO = "nova-pro"
ROUTE_HAIKU = "haiku-4.5"
ALLOWED_ROUTES = frozenset({ROUTE_NOVA_PRO, ROUTE_HAIKU})

# Documented target mapping (LiteLLM owns the authoritative copy). Kept here only
# so tooling / docs / tests can assert the contract without a live gateway.
ROUTE_TARGETS = {
    ROUTE_NOVA_PRO: "bedrock/apac.amazon.nova-pro-v1:0",
    ROUTE_HAIKU: "bedrock/apac.anthropic.claude-haiku-4-5-20251001-v1:0",
}

_DEFAULT_TIMEOUT_S = 60.0


class LLMError(RuntimeError):
    """Raised when the LiteLLM gateway call fails or returns an unusable body."""


def resolve_route(route: str) -> str:
    """Validate a route name and return it.

    Raises ``ValueError`` for anything not in :data:`ALLOWED_ROUTES` so that a
    hardcoded or mistyped model id can never leak into a request.
    """
    if route not in ALLOWED_ROUTES:
        raise ValueError(
            f"Unknown model route {route!r}. Allowed routes: "
            f"{sorted(ALLOWED_ROUTES)}. Do not pass raw Bedrock model ids."
        )
    return route


@dataclass
class LLMClient:
    """Minimal OpenAI-compatible chat client pointed at the LiteLLM gateway.

    Args:
        base_url: LiteLLM function URL. Defaults to the ``LITELLM_URL`` env var.
        timeout: Per-request timeout in seconds.
        extra_headers: Optional headers (e.g. SigV4 already-signed proxies /
            an API key when running LiteLLM behind a shared secret in dev).

    The client intentionally uses the stdlib only (``urllib``) so the agent
    runtime image stays small and has no transitive HTTP dependency to pin.
    """

    base_url: str = field(default_factory=lambda: os.environ.get("LITELLM_URL", ""))
    timeout: float = _DEFAULT_TIMEOUT_S
    extra_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_url = (self.base_url or "").rstrip("/")

    def _endpoint(self) -> str:
        if not self.base_url:
            raise LLMError(
                "LITELLM_URL is not configured. Set the LITELLM_URL env var to "
                "the LiteLLM gateway function URL before invoking the agents."
            )
        return f"{self.base_url}/chat/completions"

    def chat(
        self,
        route: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send an OpenAI-style chat completion and return the text content.

        Args:
            route: One of :data:`ALLOWED_ROUTES` (``nova-pro`` / ``haiku-4.5``).
            messages: OpenAI chat messages (``[{"role": ..., "content": ...}]``).
            temperature: Sampling temperature.
            max_tokens: Response cap.
            response_format: Optional OpenAI ``response_format`` object (e.g.
                ``{"type": "json_object"}``) to nudge structured replies.

        Returns:
            The assistant message content as a string.

        Raises:
            ValueError: If ``route`` is not an allowed route.
            LLMError: On transport failure or an unparseable/empty response.
        """
        model = resolve_route(route)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.extra_headers}
        request = urllib.request.Request(
            self._endpoint(), data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover - network path
            detail = exc.read().decode("utf-8", "replace") if exc.fp else str(exc)
            raise LLMError(
                f"LiteLLM returned HTTP {exc.code} for route {route!r}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network path
            raise LLMError(
                f"Could not reach LiteLLM at {self.base_url!r}: {exc.reason}"
            ) from exc

        return self._extract_content(body, route)

    def chat_json(
        self,
        route: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> Any:
        """Chat and parse the reply as JSON.

        Requests an OpenAI ``json_object`` response format and tolerantly
        extracts the first JSON object/array if the model wraps it in prose.
        Raises :class:`LLMError` if no JSON can be recovered.
        """
        text = self.chat(
            route,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return _loads_lenient(text)

    @staticmethod
    def _extract_content(body: str, route: str) -> str:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"LiteLLM route {route!r} returned non-JSON body: {body[:200]!r}"
            ) from exc
        try:
            return parsed["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"LiteLLM route {route!r} response missing choices/message: "
                f"{body[:200]!r}"
            ) from exc


def _loads_lenient(text: str) -> Any:
    """Parse JSON, recovering the first {...} or [...] block if wrapped in prose."""
    text = text.strip()
    if not text:
        raise LLMError("Empty response where JSON was expected.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Recover the first balanced JSON object or array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Could not parse JSON from model output: {text[:200]!r}")
