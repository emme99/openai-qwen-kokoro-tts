"""Fixture condivise: FakeEngine (sinusoide, niente torch) + client API."""

from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

try:
    import torch  # noqa: F401

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# I test che toccano service.py (e quindi torch) sono saltati in CI senza torch.
requires_torch = pytest.mark.skipif(not HAS_TORCH, reason="richiede torch (non in CI)")


class FakeEngine:
    """Engine finto per i test API: sinusoide a 24 kHz, sleep configurabile.

    Firma conforme al contratto TTSEngine: synthesize(text, *, voice, language)
    -> (samples float32, sample_rate).
    """

    name = "fake"

    def __init__(self, sleep: float = 0.0, sample_rate: int = 24000, duration: float = 0.5):
        self.sleep = sleep
        self.sample_rate = sample_rate
        self.duration = duration
        self.device = "fake"
        self.calls = 0
        self.model_loaded = False

    def load(self) -> None:
        self.model_loaded = True

    def synthesize(self, text: str, *, voice: str, language: str) -> tuple[np.ndarray, int]:
        self.calls += 1
        if self.sleep:
            time.sleep(self.sleep)
        t = np.arange(int(self.sample_rate * self.duration)) / self.sample_rate
        samples = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return samples, self.sample_rate

    def list_voices(self) -> list[str]:
        return ["alloy", "ash"]


@pytest.fixture
def fake_engine():
    return FakeEngine()


@pytest.fixture
def client(fake_engine, monkeypatch):
    """TestClient con app.engine sostituito dal FakeEngine (preload disattivato)."""
    import app as app_module

    monkeypatch.setattr(app_module, "engine", fake_engine)
    monkeypatch.setattr(app_module.settings, "preload", False)
    with TestClient(app_module.app) as c:
        yield c
