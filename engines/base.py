"""Contratto degli engine TTS.

Gli engine NON gestiscono speed né formato di output: producono sempre
`(samples float32, sample_rate)`. Speed (atempo) e conversione mp3/wav sono
centralizzati in `audio.py`, così il comportamento è identico tra engine.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class TTSEngine(Protocol):
    """Contratto che ogni engine TTS deve soddisfare."""

    name: str

    def load(self) -> None:
        """Carica il modello (import pesanti inclusi). Idempotente."""
        ...

    def synthesize(self, text: str, *, voice: str, language: str) -> tuple[np.ndarray, int]:
        """Sintetizza `text` con la voce `voice` (binding già risolto).

        Ritorna `(samples float32, sample_rate)`.
        """
        ...

    def list_voices(self) -> list[str]:
        """Voci native disponibili per questo engine."""
        ...
