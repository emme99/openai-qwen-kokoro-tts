"""Percorso unico di encoding audio: WAV, catena atempo, conversione mp3.

Le funzioni di catena (`build_atempo`) sono PURE e testabili senza ffmpeg.
Gli engine NON gestiscono speed né formato: tutto passa da qui, così il
comportamento è identico tra engine.
"""

from __future__ import annotations

import io
import logging
import subprocess

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# Limiti della catena atempo: ogni stadio ffmpeg atempo accetta [0.5, 2.0].
ATEMPO_MIN = 0.5
ATEMPO_MAX = 2.0

# Limiti API per il parametro speed.
SPEED_MIN = 0.25
SPEED_MAX = 4.0


def build_atempo(speed: float) -> list[float]:
    """Scompone `speed` in una catena di stadi atempo, ciascuno in [0.5, 2.0].

    Funzione pura e deterministica. Esempi:
        1.0 -> []
        0.7 -> [0.7]
        0.3 -> [0.5, 0.6]
        2.5 -> [2.0, 1.25]
    """
    if speed <= 0:
        raise ValueError(f"speed deve essere > 0, ricevuto {speed}")
    if abs(speed - 1.0) < 1e-9:
        return []

    stages: list[float] = []
    remaining = speed
    while abs(remaining - 1.0) > 1e-9:
        if remaining > ATEMPO_MAX:
            stages.append(ATEMPO_MAX)
            remaining /= ATEMPO_MAX
        elif remaining < ATEMPO_MIN:
            stages.append(ATEMPO_MIN)
            remaining /= ATEMPO_MIN
        else:
            stages.append(round(remaining, 6))
            break
    return stages


def apply_atempo(samples: np.ndarray, sample_rate: int, speed: float) -> np.ndarray:
    """Applica la catena atempo via ffmpeg al WAV in memoria (pitch preservato).

    speed == 1.0 -> nessun lavoro, ritorna gli stessi samples.
    """
    stages = build_atempo(speed)
    if not stages:
        return samples

    wav_buf = io.BytesIO()
    sf.write(wav_buf, samples, sample_rate, format="WAV")
    wav_buf.seek(0)

    filter_chain = ",".join(f"atempo={s:g}" for s in stages)
    process = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-filter:a", filter_chain, "-f", "wav", "pipe:1", "-v", "error"],
        input=wav_buf.read(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg atempo fallito: {process.stderr.decode(errors='replace')}")

    out_buf = io.BytesIO(process.stdout)
    out, _ = sf.read(out_buf, dtype="float32")
    return out


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Codifica samples float32 in un WAV in memoria."""
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV")
    return buf.getvalue()


def encode_mp3(samples: np.ndarray, sample_rate: int) -> bytes:
    """Converte samples float32 in mp3 via ffmpeg (stderr catturato)."""
    wav_bytes = encode_wav(samples, sample_rate)
    process = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-f", "mp3", "pipe:1", "-v", "error"],
        input=wav_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg mp3 fallito: {process.stderr.decode(errors='replace')}")
    return process.stdout


def render(
    samples: np.ndarray, sample_rate: int, speed: float, fmt: str
) -> tuple[bytes, str, str]:
    """UNICO percorso di rendering: atempo -> WAV o MP3.

    Ritorna (audio_bytes, media_type, filename). Gli engine non devono mai
    codificare: passano (samples, sr) e tutto il resto avviene qui, così il
    comportamento è identico tra engine.
    """
    out = apply_atempo(samples, sample_rate, speed)
    if fmt == "mp3":
        return encode_mp3(out, sample_rate), "audio/mpeg", "speech.mp3"
    return encode_wav(out, sample_rate), "audio/wav", "speech.wav"
