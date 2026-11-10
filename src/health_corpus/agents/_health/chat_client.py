"""Thin HTTP client for a local/custom digest chat endpoint.

Expects POST ``{url}`` with ``{"message": "..."}`` and a JSON response
containing ``{"answer": "..."}``. Auth uses
``HEALTH_CORPUS_CHAT_TOKEN`` as a Bearer token when set.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

DEFAULT_CHAT_URL = "http://127.0.0.1:8200/chat"
DEFAULT_TIMEOUT_S = 120.0


class ChatApiError(RuntimeError):
    """Raised when the digest chat call fails."""


def chat(
    message: str,
    *,
    session_id: Optional[str] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    url: str | None = None,
) -> str:
    """POST ``message`` to the configured chat endpoint and return the answer."""
    endpoint = url or os.environ.get("HEALTH_CORPUS_CHAT_URL", DEFAULT_CHAT_URL)
    token = os.environ.get("HEALTH_CORPUS_CHAT_TOKEN")
    if not token:
        raise ChatApiError(
            "HEALTH_CORPUS_CHAT_TOKEN is not set; cannot call the digest chat endpoint."
        )

    payload: dict[str, str] = {"message": message}
    if session_id is not None:
        payload["session_id"] = session_id

    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = httpx.post(endpoint, json=payload, headers=headers, timeout=timeout_s)
    except httpx.HTTPError as exc:
        raise ChatApiError(f"chat transport error: {exc}") from exc

    if resp.status_code != 200:
        snippet = resp.text[:200].replace("\n", " ")
        raise ChatApiError(f"chat returned {resp.status_code}: {snippet}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise ChatApiError(f"chat returned non-JSON: {exc}") from exc

    answer = data.get("answer")
    if not isinstance(answer, str):
        raise ChatApiError(f"chat response missing 'answer' string field: {data}")
    return answer
