"""Tests for the thin HTTP wrapper around the digest chat endpoint."""
from __future__ import annotations

import pytest
import respx
from httpx import Response


def test_chat_returns_answer_field(monkeypatch):
    from health_corpus.agents._health import chat_client

    monkeypatch.setenv("HEALTH_CORPUS_CHAT_TOKEN", "tok123")
    with respx.mock:
        respx.post("http://127.0.0.1:8200/chat").mock(
            return_value=Response(200, json={"answer": "hello", "session_id": "s1"})
        )
        out = chat_client.chat("Tell me about my week")
    assert out == "hello"


def test_chat_sends_authorization_and_message(monkeypatch):
    from health_corpus.agents._health import chat_client

    monkeypatch.setenv("HEALTH_CORPUS_CHAT_TOKEN", "tok123")
    with respx.mock:
        route = respx.post("http://127.0.0.1:8200/chat").mock(
            return_value=Response(200, json={"answer": "ok"})
        )
        chat_client.chat("Tell me about my week")

    assert route.called
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer tok123"
    import json as _json

    body = _json.loads(req.content)
    assert body["message"] == "Tell me about my week"


def test_chat_non_200_raises(monkeypatch):
    from health_corpus.agents._health import chat_client

    monkeypatch.setenv("HEALTH_CORPUS_CHAT_TOKEN", "tok123")
    with respx.mock:
        respx.post("http://127.0.0.1:8200/chat").mock(
            return_value=Response(502, text="bad gateway")
        )
        with pytest.raises(chat_client.ChatApiError) as excinfo:
            chat_client.chat("hi")
    assert "502" in str(excinfo.value)


def test_chat_missing_token_raises(monkeypatch):
    from health_corpus.agents._health import chat_client

    monkeypatch.delenv("HEALTH_CORPUS_CHAT_TOKEN", raising=False)
    with pytest.raises(chat_client.ChatApiError) as excinfo:
        chat_client.chat("hi")
    assert "HEALTH_CORPUS_CHAT_TOKEN" in str(excinfo.value)


def test_chat_passes_session_id_when_provided(monkeypatch):
    from health_corpus.agents._health import chat_client

    monkeypatch.setenv("HEALTH_CORPUS_CHAT_TOKEN", "tok123")
    with respx.mock:
        route = respx.post("http://127.0.0.1:8200/chat").mock(
            return_value=Response(200, json={"answer": "ok"})
        )
        chat_client.chat("hi", session_id="abc-123")

    import json as _json

    body = _json.loads(route.calls.last.request.content)
    assert body["session_id"] == "abc-123"
