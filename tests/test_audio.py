"""Test T1.1: catena atempo pura + encoding."""

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
