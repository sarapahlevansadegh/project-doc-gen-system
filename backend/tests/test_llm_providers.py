"""Tests for the LLM provider abstraction layer.

Verifies provider selection, default model resolution, and per-provider
request formatting. Network calls are mocked so tests run offline.
"""
from __future__ import annotations

import os

import pytest


def test_default_provider_is_anthropic(monkeypatch):
    from agent.llm import _provider_from_env

    monkeypatch.delenv("DOCGEN_LLM_PROVIDER", raising=False)
    with pytest.raises(KeyError):
        os.environ["DOCGEN_LLM_PROVIDER"]
    assert _provider_from_env() == "anthropic"


def test_provider_selected_via_env(monkeypatch):
    from agent.llm import _provider_from_env

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "openai")
    assert _provider_from_env() == "openai"

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "ollama")
    assert _provider_from_env() == "ollama"

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "groq")
    assert _provider_from_env() == "groq"


def test_default_model_anthropic(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.delenv("DOCGEN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DOCGEN_ANTHROPIC_MODEL", raising=False)
    client = LLMClient(provider="anthropic")
    assert client.model == "claude-3-5-sonnet-20241022"


def test_default_model_groq(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "groq")
    monkeypatch.delenv("DOCGEN_GROQ_MODEL", raising=False)
    client = LLMClient(provider="groq")
    assert client.model == "llama-3.3-70b-versatile"


def test_default_model_openai(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "openai")
    monkeypatch.delenv("DOCGEN_OPENAI_MODEL", raising=False)
    client = LLMClient(provider="openai")
    assert client.model == "gpt-4o-mini"


def test_default_model_ollama(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "ollama")
    monkeypatch.delenv("DOCGEN_OLLAMA_MODEL", raising=False)
    client = LLMClient(provider="ollama")
    assert client.model == "llama3.1"


def test_model_override_via_env(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "openai")
    monkeypatch.setenv("DOCGEN_OPENAI_MODEL", "gpt-4o")
    client = LLMClient(provider="openai")
    assert client.model == "gpt-4o"


def test_model_override_via_constructor():
    from agent.llm import LLMClient

    client = LLMClient(provider="openai", model="custom-model")
    assert client.model == "custom-model"


def test_generate_fn_bypass_for_all_providers():
    from agent.llm import LLMClient

    providers = ["anthropic", "groq", "openai", "ollama"]
    for provider in providers:
        client = LLMClient(provider=provider, generate_fn=lambda p, mt, t: f"fake-{provider}")
        result = client.generate("hello", 100, 0.5)
        assert result == f"fake-{provider}"


def test_anthropic_generate_formats_request(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "anthropic")

    class FakeMessages:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.last_call = kwargs
            class Block:
                text = "anthropic-result"
            class Resp:
                content = [Block()]
            return Resp()

    class FakeAnthropic:
        def __init__(self, api_key):
            self.api_key = api_key
            self.last_call = None
            self.messages = FakeMessages(self)

    client = LLMClient(provider="anthropic")
    client._client = FakeAnthropic(api_key="test-key")
    result = client.generate("prompt-text", 500, 0.7)
    assert result == "anthropic-result"
    assert client._client.last_call["model"] == "claude-3-5-sonnet-20241022"
    assert client._client.last_call["max_tokens"] == 500
    assert client._client.last_call["temperature"] == 0.7


def test_groq_generate_formats_request(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "groq")

    class FakeCompletions:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.last_call = kwargs
            class Choice:
                message = type("Msg", (), {"content": "groq-result"})()
            class Resp:
                choices = [Choice()]
            return Resp()

    class FakeChat:
        def __init__(self, outer):
            self.outer = outer
            self.completions = FakeCompletions(outer)

    class FakeGroq:
        def __init__(self, api_key):
            self.api_key = api_key
            self.last_call = None
            self.chat = FakeChat(self)

    client = LLMClient(provider="groq")
    client._client = FakeGroq(api_key="test-key")
    result = client.generate("prompt-text", 300, 0.4)
    assert result == "groq-result"
    assert client._client.last_call["model"] == "llama-3.3-70b-versatile"
    assert client._client.last_call["max_tokens"] == 300
    assert client._client.last_call["temperature"] == 0.4


def test_openai_generate_formats_request(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "openai")

    class FakeCompletions:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.last_call = kwargs
            class Choice:
                message = type("Msg", (), {"content": "openai-result"})()
            class Resp:
                choices = [Choice()]
            return Resp()

    class FakeChat:
        def __init__(self, outer):
            self.outer = outer
            self.completions = FakeCompletions(outer)

    class FakeOpenAI:
        def __init__(self, api_key, base_url=None):
            self.api_key = api_key
            self.base_url = base_url
            self.last_call = None
            self.chat = FakeChat(self)

    client = LLMClient(provider="openai")
    client._client = FakeOpenAI(api_key="test-key")
    result = client.generate("prompt-text", 200, 0.2)
    assert result == "openai-result"
    assert client._client.last_call["model"] == "gpt-4o-mini"
    assert client._client.last_call["max_tokens"] == 200
    assert client._client.last_call["temperature"] == 0.2


def test_ollama_generate_formats_request(monkeypatch):
    from agent.llm import LLMClient

    monkeypatch.setenv("DOCGEN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DOCGEN_OLLAMA_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("DOCGEN_OLLAMA_MODEL", raising=False)

    
    class FakeCompletions:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.last_call = kwargs
            class Choice:
                message = type("Msg", (), {"content": "ollama-result"})()
            class Resp:
                choices = [Choice()]
            return Resp()

    class FakeChat:
        def __init__(self, outer):
            self.outer = outer
            self.completions = FakeCompletions(outer)

    class FakeOpenAI:
        def __init__(self, api_key, base_url=None):
            self.api_key = api_key
            self.base_url = base_url
            self.last_call = None
            self.chat = FakeChat(self)

    client = LLMClient(provider="ollama")
    client._client = FakeOpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
    result = client.generate("prompt-text", 150, 0.1)
    assert result == "ollama-result"
    assert client._client.last_call["model"] == "llama3.1"
    assert client._client.last_call["max_tokens"] == 150
    assert client._client.last_call["temperature"] == 0.1


def test_get_llm_client_returns_instance(monkeypatch):
    from agent.llm import get_llm_client

    monkeypatch.delenv("DOCGEN_LLM_PROVIDER", raising=False)
    client = get_llm_client()
    assert isinstance(client, type(client))
    assert client.provider == "anthropic"


def test_get_llm_client_with_generate_fn():
    from agent.llm import get_llm_client

    def fake(p, mt, t):
        return "injected"

    client = get_llm_client(generate_fn=fake)
    assert client.generate("anything", 10, 0.0) == "injected"
