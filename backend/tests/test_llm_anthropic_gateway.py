"""Tests for the anthropic provider: gateway auth and response parsing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.llm import LLMClient
from config import settings


class _FakeAnthropic:
    """Stands in for anthropic.Anthropic and records constructor kwargs."""

    last_kwargs: dict = {}
    response: SimpleNamespace | None = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **_kwargs):
        return type(self).response


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


@pytest.fixture(autouse=True)
def _fake_sdk(monkeypatch):
    monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropic)
    _FakeAnthropic.last_kwargs = {}
    _FakeAnthropic.response = None


def test_gateway_uses_bearer_token_and_base_url(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_base_url", "https://coarena.ai/api")
    monkeypatch.setattr(settings, "anthropic_auth_token", "coa_test")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    LLMClient(provider="anthropic", model="m")._get_client()

    kwargs = _FakeAnthropic.last_kwargs
    assert kwargs["base_url"] == "https://coarena.ai/api"
    assert kwargs["auth_token"] == "coa_test"
    assert "api_key" not in kwargs


def test_without_token_falls_back_to_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_base_url", "")
    monkeypatch.setattr(settings, "anthropic_auth_token", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")

    LLMClient(provider="anthropic", model="m")._get_client()

    kwargs = _FakeAnthropic.last_kwargs
    assert kwargs["base_url"] == "https://api.anthropic.com"
    assert kwargs["api_key"] == "sk-test"
    assert "auth_token" not in kwargs


def test_response_joins_text_blocks_and_skips_others():
    _FakeAnthropic.response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="internal"),
            _text_block("Hello "),
            _text_block("world "),
        ],
        stop_reason="end_turn",
    )

    client = LLMClient(provider="anthropic", model="m")

    assert client.generate("hi") == "Hello world"


def test_empty_response_raises_clear_error():
    _FakeAnthropic.response = SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking="only thoughts")],
        stop_reason="max_tokens",
    )

    client = LLMClient(provider="anthropic", model="m")

    with pytest.raises(RuntimeError, match="no text"):
        client.generate("hi")
