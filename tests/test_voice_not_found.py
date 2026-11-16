"""Test T0.3: nessun fallback rumoroso, VoiceNotFound con elenco voci."""

import os

import pytest

from errors import VoiceNotFound
from tests.conftest import requires_torch


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """Service con voices/ in una cartella temporanea e modello finto."""
    from service import QwenTTSService  # import pesante (torch): solo nel test

    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "alloy.wav").write_bytes(b"RIFF-fake")
    (voices / "ash.wav").write_bytes(b"RIFF-fake")

    s = QwenTTSService(model_path=str(tmp_path / "model"), device="cpu")
    s.voices_dir = str(voices)
    s.cache_dir = str(voices / "cache")
    os.makedirs(s.cache_dir, exist_ok=True)
    # Evita il caricamento del modello reale: la risoluzione voce precede l'inferenza.
    s.model = object()
    return s


@requires_torch
def test_voice_not_found_raises_with_available(svc):
    with pytest.raises(VoiceNotFound) as exc:
        svc.synthesize("ciao", voice_ref_path="inesistente", lang="it", format="wav")
    msg = str(exc.value)
    assert "inesistente" in msg
    assert "alloy" in msg and "ash" in msg


@requires_torch
def test_no_default_wav_created(svc, tmp_path):
    with pytest.raises(VoiceNotFound):
        svc.synthesize("ciao", voice_ref_path="inesistente", lang="it", format="wav")
    # Nessun file creato in voices/ (in particolare niente default.wav da rumore)
    created = [f for f in os.listdir(svc.voices_dir) if f != "cache"]
    assert "default.wav" not in created
    assert sorted(f[: -4] for f in created if f.endswith(".wav")) == ["alloy", "ash"]


@requires_torch
def test_existing_voice_resolves(svc):
    # alloy.wav esiste: la risoluzione deve trovare il file (poi fallisce in inferenza
    # finta, ma NON con VoiceNotFound).
    try:
        svc.synthesize("ciao", voice_ref_path="alloy", lang="it", format="wav")
    except VoiceNotFound:
        pytest.fail("alloy esiste: non deve alzare VoiceNotFound")
    except Exception:
        # Atteso: il modello finto non sa sintetizzare.
        pass
