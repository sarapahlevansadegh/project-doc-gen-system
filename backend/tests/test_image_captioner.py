"""Unit tests for rag/image_captioner.py.

Focus: the feature-flag gate and fail-soft fallback behavior, not the real
OpenRouter network call (which is mocked out).
"""
from __future__ import annotations

import importlib

import pytest

import rag.image_captioner as captioner


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.delenv("DOCGEN_ENABLE_FIGURE_CAPTIONING", raising=False)
    monkeypatch.delenv("DOCGEN_OPENROUTER_VISION_MODEL", raising=False)
    yield


def test_disabled_by_default_returns_none(tmp_path):
    img = tmp_path / "fig1.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal fake PNG header, content irrelevant
    assert captioner.captioning_enabled() is False
    assert captioner.caption_image(img) is None


def test_missing_api_key_short_circuits(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCGEN_ENABLE_FIGURE_CAPTIONING", "true")
    monkeypatch.setattr(captioner.settings, "openrouter_api_key", "", raising=False)
    img = tmp_path / "fig1.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert captioner.caption_image(img) is None


def test_missing_image_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCGEN_ENABLE_FIGURE_CAPTIONING", "true")
    monkeypatch.setattr(captioner.settings, "openrouter_api_key", "fake-key", raising=False)
    assert captioner.caption_image(tmp_path / "does_not_exist.png") is None


def test_falls_back_to_second_model_on_empty_content(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCGEN_ENABLE_FIGURE_CAPTIONING", "true")
    monkeypatch.setenv(
        "DOCGEN_OPENROUTER_VISION_MODEL", "reasoning-model:free,good-model:free"
    )
    monkeypatch.setattr(captioner.settings, "openrouter_api_key", "fake-key", raising=False)

    img = tmp_path / "fig1.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    calls: list[str] = []

    def _fake_call(model: str, data_url: str) -> str | None:
        calls.append(model)
        if model == "reasoning-model:free":
            return None  # simulates the empty-content failure mode
        return "A wiring diagram showing sensor connections."

    monkeypatch.setattr(captioner, "_call_vision_model", _fake_call)

    result = captioner.caption_image(img)

    assert result == "A wiring diagram showing sensor connections."
    assert calls == ["reasoning-model:free", "good-model:free"]


def test_all_models_failing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCGEN_ENABLE_FIGURE_CAPTIONING", "true")
    monkeypatch.setenv("DOCGEN_OPENROUTER_VISION_MODEL", "bad-model:free")
    monkeypatch.setattr(captioner.settings, "openrouter_api_key", "fake-key", raising=False)

    img = tmp_path / "fig1.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    def _raise(model: str, data_url: str) -> str | None:
        raise RuntimeError("network error")

    monkeypatch.setattr(captioner, "_call_vision_model", _raise)

    assert captioner.caption_image(img) is None


def test_vision_models_parses_csv_and_strips_whitespace(monkeypatch):
    monkeypatch.setenv("DOCGEN_OPENROUTER_VISION_MODEL", " model-a:free , model-b:free ")
    assert captioner._vision_models() == ["model-a:free", "model-b:free"]


def test_vision_models_default_when_unset():
    models = captioner._vision_models()
    assert models == ["google/gemma-4-31b-it:free", "minimax/minimax-m3:free"]
