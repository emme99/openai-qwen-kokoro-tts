"""Test T2.1: contratto engine + factory."""

from __future__ import annotations

import pytest

from config import Settings
from engines import make_engine
from engines.base import TTSEngine


def _settings(engine: str) -> Settings:
    return Settings.load(env={"TTS_ENGINE": engine}, config_json_path="/nonexistent.json")


def test_factory_qwen():
    e = make_engine(_settings("qwen"))
    assert e.name == "qwen"
    assert isinstance(e, TTSEngine)


def test_factory_unknown_raises():
    with pytest.raises(ValueError, match="TTS_ENGINE sconosciuto"):
        make_engine(_settings("nonexistent"))


def test_qwen_engine_importable_without_model():
    """QwenEngine è costruisibile senza caricare il modello (lazy)."""
    from engines.qwen import QwenEngine

    e = QwenEngine(_settings("qwen"))
    assert e.model_loaded is False
    assert e.device == "mps"
