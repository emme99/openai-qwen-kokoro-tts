"""Test T1.4: guardrail MAX_INPUT_CHARS + cache max 2 file per voce."""

from __future__ import annotations

import os

import pytest

import app as app_module
from service import QwenTTSService

# --- Guardrail input ---

def test_input_too_long_400(client, monkeypatch):
    monkeypatch.setattr(app_module.settings, "max_input_chars", 100)
    r = client.post("/v1/audio/speech", json={"input": "x" * 3000, "voice": "alloy"})
    assert r.status_code == 400
    assert "troppo lungo" in r.json()["detail"]


def test_input_at_limit_ok(client, monkeypatch):
    monkeypatch.setattr(app_module.settings, "max_input_chars", 100)
    r = client.post("/v1/audio/speech", json={"input": "x" * 100, "voice": "alloy"})
    assert r.status_code == 200


# --- Cache: max 2 file per voce ---

@pytest.fixture
def svc(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    s = QwenTTSService(model_path=str(tmp_path / "model"), device="cpu")
    s.voices_dir = str(voices)
    s.cache_dir = str(voices / "cache")
    os.makedirs(s.cache_dir, exist_ok=True)
    return s


def _cache_files(svc, voice="alloy"):
    prefix = f"{voice}_"
    return sorted(
        f for f in os.listdir(svc.cache_dir)
        if f.startswith(prefix) and f.endswith(".pt")
    )


def test_prune_keeps_two_newest(svc):
    # 3 mtime diversi per la stessa voce
    for mtime in (1000.0, 2000.0, 3000.0):
        path = os.path.join(svc.cache_dir, f"alloy.wav_{mtime}.pt")
        with open(path, "wb") as f:
            f.write(b"fake")
    svc._prune_voice_cache("alloy.wav", keep=2)
    remaining = _cache_files(svc, "alloy.wav")
    assert remaining == ["alloy.wav_2000.0.pt", "alloy.wav_3000.0.pt"]


def test_prune_noop_when_under_limit(svc):
    for mtime in (1000.0, 2000.0):
        with open(os.path.join(svc.cache_dir, f"alloy.wav_{mtime}.pt"), "wb") as f:
            f.write(b"fake")
    svc._prune_voice_cache("alloy.wav", keep=2)
    assert len(_cache_files(svc, "alloy.wav")) == 2


def test_prune_does_not_touch_other_voices(svc):
    for mtime in (1000.0, 2000.0, 3000.0):
        with open(os.path.join(svc.cache_dir, f"alloy.wav_{mtime}.pt"), "wb") as f:
            f.write(b"fake")
    with open(os.path.join(svc.cache_dir, "ash.wav_1000.0.pt"), "wb") as f:
        f.write(b"fake")
    svc._prune_voice_cache("alloy.wav", keep=2)
    # ash intatto
    assert "ash.wav_1000.0.pt" in os.listdir(svc.cache_dir)
    assert len(_cache_files(svc, "alloy.wav")) == 2
