"""LLM provider abstraction layer.

Supports multiple providers selected via environment:

- anthropic
- groq
- openai
- ollama
- openrouter
- gemini

API keys/URLs are loaded from environment settings.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from config import settings


LLMProvider = str

ANTHROPIC = "anthropic"
GROQ = "groq"
OPENAI = "openai"
OLLAMA = "ollama"
OPENROUTER = "openrouter"
GEMINI = "gemini"


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class GenerationResult:
    text: str


GenerateFn = Callable[[str, int, float], str]


def _provider_from_env() -> LLMProvider:
    return (
        os.getenv(
            "DOCGEN_LLM_PROVIDER",
            settings.llm_provider,
        )
        .lower()
        .strip()
    )


def _http_client():
    try:
        import httpx

        return httpx.Client(
            headers={
                "User-Agent": _USER_AGENT
            },
            timeout=httpx.Timeout(
                120.0,
                connect=15.0,
            ),
        )

    except ImportError:
        return None


class LLMClient:

    def __init__(
        self,
        provider: LLMProvider | None = None,
        model: str | None = None,
        generate_fn: GenerateFn | None = None,
    ):

        self.provider = provider or _provider_from_env()

        self.model = (
            model
            or self._default_model()
        )

        self._generate_fn = generate_fn
        self._client: Any = None


    def _default_model(self) -> str:

        models = {

            GROQ: (
                "DOCGEN_GROQ_MODEL",
                "llama-3.3-70b-versatile",
            ),

            OPENAI: (
                "DOCGEN_OPENAI_MODEL",
                "gpt-4o-mini",
            ),

            OLLAMA: (
                "DOCGEN_OLLAMA_MODEL",
                "llama3.1",
            ),

            OPENROUTER: (
                "DOCGEN_OPENROUTER_MODEL",
                "google/gemini-2.5-pro",
            ),

            GEMINI: (
                "DOCGEN_LLM_MODEL",
                "gemini-2.5-flash",
            ),

            ANTHROPIC: (
                "DOCGEN_ANTHROPIC_MODEL",
                "claude-3-5-sonnet-20241022",
            ),
        }


        if self.provider not in models:
            raise ValueError(
                f"Unsupported LLM provider: {self.provider}"
            )


        env_name, default = models[self.provider]


        return os.getenv(
            env_name,
            default,
        )


    def _get_client(self):

        if self._client is not None:
            return self._client


        http_client = _http_client()


        if self.provider == GROQ:

            from groq import Groq

            self._client = Groq(
                api_key=settings.groq_api_key,
                http_client=http_client,
            )


        elif self.provider == OPENAI:

            from openai import OpenAI

            self._client = OpenAI(
                api_key=settings.openai_api_key,
                http_client=http_client,
            )


        elif self.provider == OLLAMA:

            from openai import OpenAI

            self._client = OpenAI(
                base_url=settings.ollama_url,
                api_key="ollama",
                http_client=http_client,
            )


        elif self.provider == OPENROUTER:

            from openai import OpenAI

            self._client = OpenAI(
                base_url=(
                    "https://openrouter.ai/api/v1"
                ),
                api_key=settings.openrouter_api_key,
                http_client=http_client,
            )


        elif self.provider == GEMINI:

            from openai import OpenAI

            self._client = OpenAI(
                base_url=(
                    "https://generativelanguage.googleapis.com/v1beta/openai/"
                ),
                api_key=settings.gemini_api_key,
                http_client=http_client,
            )


        elif self.provider == ANTHROPIC:

            from anthropic import Anthropic

            self._client = Anthropic(
                api_key=settings.anthropic_api_key,
                http_client=http_client,
            )


        else:
            raise ValueError(
                f"Unsupported provider {self.provider}"
            )


        return self._client



    def generate(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> str:


        if self._generate_fn:
            return self._generate_fn(
                prompt,
                max_tokens,
                temperature,
            )


        client = self._get_client()


        OPENAI_STYLE_PROVIDERS = {
            GROQ,
            OPENAI,
            OLLAMA,
            OPENROUTER,
            GEMINI,
        }


        if self.provider in OPENAI_STYLE_PROVIDERS:

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )


            return (
                response
                .choices[0]
                .message
                .content
                .strip()
            )


        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )


        return response.content[0].text.strip()



def get_llm_client(
    generate_fn: GenerateFn | None = None,
) -> LLMClient:

    return LLMClient(
        generate_fn=generate_fn
    )