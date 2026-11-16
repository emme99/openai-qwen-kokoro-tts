"""Test T1.1: catena atempo pura + encoding. T2.2: percorso unico render()."""

import hashlib
import io
import subprocess

import numpy as np
import pytest
import soundfile as sf

import audio

# --- build_atempo: funzione pura ---

def test_atempo_identity():
    assert audio.build_atempo(1.0) == []


def test_atempo_single_stage():
    assert audio.build_atempo(0.7) == [0.7]
    assert audio.build_atempo(1.5) == [1.5]


def test_atempo_multi_stage_slow():
    # 0.3 -> [0.5, 0.6]
    assert audio.build_atempo(0.3) == [0.5, 0.6]


def test_atempo_multi_stage_fast():
    # 2.5 -> [2.0, 1.25]
    assert audio.build_atempo(2.5) == [2.0, 1.25]


def test_atempo_product_equals_speed():
    for speed in (0.25, 0.3, 0.5, 0.7, 1.0, 1.3, 2.0, 2.5, 4.0):
        stages = audio.build_atempo(speed)
        product = 1.0
        for s in stages:
            product *= s
        assert product == pytest.approx(speed, rel=1e-6), f"speed={speed} stages={stages}"


def test_atempo_stages_in_range():
    for speed in (0.25, 0.3, 0.7, 1.5, 2.5, 4.0):
        for s in audio.build_atempo(speed):
            assert audio.ATEMPO_MIN <= s <= audio.ATEMPO_MAX


def test_atempo_invalid_speed():
    with pytest.raises(ValueError):
        audio.build_atempo(0)
    with pytest.raises(ValueError):
        audio.build_atempo(-1)


# --- apply_atempo: durata reale via ffmpeg ---

def _duration_seconds(wav_bytes: bytes, tmp_path) -> float:
    # ffprobe non legge la durata da pipe: si usa un file temporaneo.
    f = tmp_path / "probe.wav"
    f.write_bytes(wav_bytes)
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return float(proc.stdout.decode().strip())


def test_apply_atempo_duration_slowdown(tmp_path):
    sr = 24000
    # 1 secondo di sinusoide
    t = np.arange(sr) / sr
    samples = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    out = audio.apply_atempo(samples, sr, 0.3)
    wav_bytes = audio.encode_wav(out, sr)
    duration = _duration_seconds(wav_bytes, tmp_path)
    # 1s / 0.3 = 3.33s, tolleranza 10%
    assert duration == pytest.approx(3.333, rel=0.10)


def test_apply_atempo_identity_noop():
    sr = 24000
    samples = np.zeros(sr, dtype=np.float32)
    out = audio.apply_atempo(samples, sr, 1.0)
    assert out is samples  # nessun lavoro, stesso oggetto


# --- encoding ---

def test_encode_wav_roundtrip():
    sr = 24000
    samples = np.zeros(sr, dtype=np.float32)
    wav_bytes = audio.encode_wav(samples, sr)
    out, out_sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    assert out_sr == sr
    assert len(out) == sr


def test_encode_mp3_produces_valid_mp3():
    sr = 24000
    t = np.arange(sr) / sr
    samples = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    mp3_bytes = audio.encode_mp3(samples, sr)
    # Verifica che ffprobe lo riconosca come mp3 (durata N/A su pipe: si usa format_name)
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "csv=p=0", "-"],
        input=mp3_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert "mp3" in proc.stdout.decode().strip()
    assert len(mp3_bytes) > 1000


# --- T2.2: render() è l'unico percorso di encoding ---

def _golden_sine(sr: int = 24000, seconds: float = 0.5, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_render_wav_golden_sha256():
    """Golden test: stessa sinusoide in ingresso -> stesso SHA256 del WAV in uscita."""
    samples = _golden_sine()
    buf1, media1, name1 = audio.render(samples, 24000, 1.0, "wav")
    buf2, media2, name2 = audio.render(_golden_sine(), 24000, 1.0, "wav")
    assert media1 == media2 == "audio/wav"
    assert name1 == name2 == "speech.wav"
    assert hashlib.sha256(buf1).hexdigest() == hashlib.sha256(buf2).hexdigest()


def test_render_wav_matches_encode_wav():
    """render() con speed=1.0 equivale a encode_wav() (nessun atempo)."""
    samples = _golden_sine()
    buf, media, name = audio.render(samples, 24000, 1.0, "wav")
    assert buf == audio.encode_wav(samples, 24000)


def test_render_mp3_golden_sha256():
    """Golden test mp3: stessa sinusoide -> stesso SHA256 (ffmpeg deterministico)."""
    samples = _golden_sine()
    buf1, media1, name1 = audio.render(samples, 24000, 1.0, "mp3")
    buf2, media2, name2 = audio.render(_golden_sine(), 24000, 1.0, "mp3")
    assert media1 == media2 == "audio/mpeg"
    assert name1 == name2 == "speech.mp3"
    assert hashlib.sha256(buf1).hexdigest() == hashlib.sha256(buf2).hexdigest()


def test_render_applies_atempo(tmp_path):
    """render() con speed != 1.0 cambia la durata (atempo applicato)."""
    sr = 24000
    samples = _golden_sine(seconds=1.0)
    buf, _, _ = audio.render(samples, sr, 2.0, "wav")
    duration = _duration_seconds(buf, tmp_path)
    # 1s / 2.0 = 0.5s, tolleranza 10%
    assert duration == pytest.approx(0.5, rel=0.10)
