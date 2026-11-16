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


def test_factory_kokoro():
    e = make_engine(_settings("kokoro"))
    assert e.name == "kokoro"
    assert isinstance(e, TTSEngine)


def test_kokoro_engine_importable_without_model():
    """KokoroEngine è costruisibile senza kokoro-onnx né modello (lazy)."""
    from engines.kokoro import KokoroEngine

    e = KokoroEngine(_settings("kokoro"))
    assert e.model_loaded is False
    assert e.device == "cpu"
    assert e.list_voice_files() == []


def test_kokoro_list_voices_from_npz(tmp_path):
    """list_voices() legge gli id dal file voices (npz) senza il modello onnx."""
    import numpy as np

    # np.savez aggiunge .npz se l'estensione non è già .npz
    voices = tmp_path / "voices-v1.0.bin.npz"
    np.savez(
        voices,
        if_sara=np.zeros((510, 1, 256), dtype=np.float32),
        af_heart=np.zeros((510, 1, 256), dtype=np.float32),
    )
    s = _settings("kokoro")
    s.kokoro_voices_path = str(voices)
    from engines.kokoro import KokoroEngine

    assert KokoroEngine(s).list_voices() == ["af_heart", "if_sara"]


def test_kokoro_list_voices_missing_file():
    from engines.kokoro import KokoroEngine

    s = _settings("kokoro")
    s.kokoro_voices_path = "/nonexistent/voices.bin"
    assert KokoroEngine(s).list_voices() == []
