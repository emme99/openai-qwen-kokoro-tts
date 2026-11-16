"""Fixture condivise: FakeEngine (sinusoide, niente torch) + client API."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient


class FakeEngine:
    """Engine finto per i test API: sinusoide a 24 kHz, sleep configurabile.

    Firma compatibile con QwenTTSService.synthesize (ritorna un buffer WAV).
    """

    def __init__(self, sleep: float = 0.0, sample_rate: int = 24000, duration: float = 0.5):
        self.sleep = sleep
        self.sample_rate = sample_rate
        self.duration = duration
        self.device = "fake"
        self.calls = 0
        self.model = None  # per /health (model_loaded)

    def synthesize(self, text: str, voice_ref_path: str = None, lang: str = "it", format: str = "wav"):
        import time

        self.calls += 1
        if self.sleep:
            time.sleep(self.sleep)
        t = np.arange(int(self.sample_rate * self.duration)) / self.sample_rate
        samples = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        buf = io.BytesIO()
        sf.write(buf, samples, self.sample_rate, format="WAV")
        buf.seek(0)
        return buf

    def list_voices(self) -> list[str]:
        return ["alloy", "ash"]

    def load_model(self):
        """No-op: il modello finto è sempre 'caricato'."""
        pass


@pytest.fixture
def fake_engine():
    return FakeEngine()


@pytest.fixture
def client(fake_engine, monkeypatch):
    """TestClient con app.tts_service sostituito dal FakeEngine."""
    import app as app_module

    monkeypatch.setattr(app_module, "tts_service", fake_engine)
    with TestClient(app_module.app) as c:
        yield c
