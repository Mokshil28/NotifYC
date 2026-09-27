"""xAI Responses API client.

Documented call: POST https://api.x.ai/v1/responses
Authorization: Bearer $XAI_API_KEY
Model shown in the current text guide: grok-4.6
``store: false`` keeps the exchange off xAI's server-side conversation store.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-4.6"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 400


class GrokUnavailable(Exception):
    """The Responses API could not be called."""


class GrokResponseError(Exception):
    """The API answered, but the body was not usable text."""


def request_body(model: str, system: str, user: str) -> dict[str, Any]:
    return {
        "model": model,
        "store": False,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }


def extract_output_text(payload: dict[str, Any]) -> str:
    """Read assistant text from the documented Responses ``output`` items."""
    output = payload.get("output")
    if not isinstance(output, list):
        raise GrokResponseError("Grok response did not include an output list.")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
    if not parts:
        raise GrokResponseError("Grok response did not include output text.")
    return "\n".join(parts)


class XaiResponsesClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        url: str = API_URL,
        opener: Any = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.url = url
        self._opener = opener

    @classmethod
    def from_env(cls) -> XaiResponsesClient:
        api_key = os.environ.get("XAI_API_KEY", "").strip()
        if not api_key:
            raise GrokUnavailable("XAI_API_KEY is not set.")
        model = os.environ.get("XAI_MODEL", "").strip() or DEFAULT_MODEL
        timeout = _timeout(os.environ.get("XAI_TIMEOUT_SECONDS"))
        return cls(api_key, model=model, timeout=timeout)

    def complete(self, system: str, user: str) -> str:
        body = request_body(self.model, system, user)
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        open_request = self._opener or urllib.request.urlopen
        try:
            with open_request(request, timeout=self.timeout) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raise GrokUnavailable(f"Grok request failed with HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise GrokUnavailable("Grok request could not reach the API.") from exc
        except TimeoutError as exc:
            raise GrokUnavailable("Grok request timed out.") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GrokResponseError("Grok response was not JSON.") from exc
        if not isinstance(payload, dict):
            raise GrokResponseError("Grok response was not a JSON object.")
        return extract_output_text(payload)


def _timeout(value: str | None) -> float:
    if not value:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        parsed = float(value)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    if parsed <= 0:
        return DEFAULT_TIMEOUT_SECONDS
    return parsed
