"""Wrapper Kokoro-82M (kokoro-onnx, CPU): incapsula Kokoro nel contratto TTSEngine.

Gli import pesanti (kokoro_onnx, onnxruntime) avvengono dentro `load()`,
mai a livello di modulo: così questo file è importabile anche senza
kokoro-onnx installato (necessario per la suite di test in CI).
"""

from __future__ import annotations

import logging

import numpy as np

from config import Settings

logger = logging.getLogger(__name__)

# Mappa lingua logica -> codice lingua di kokoro-onnx (espeak-ng/misaki).
_LANG_CODES = {
    "it": "it",
    "en": "en-us",
}


class KokoroEngine:
    """Engine Kokoro-82M via kokoro-onnx (CPU)."""

    name = "kokoro"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._k = None  # istanziato dentro load()

    @property
    def model_loaded(self) -> bool:
        return self._k is not None

    def load(self) -> None:
        if self._k is not None:
            return
        # Import pesante: trascina onnxruntime/phonemizer. Solo qui, non a livello modulo.
        from kokoro_onnx import Kokoro

        logger.info(
            "Carico KokoroEngine: model=%s voices=%s",
            self._settings.kokoro_model_path,
            self._settings.kokoro_voices_path,
        )
        self._k = Kokoro(self._settings.kokoro_model_path, self._settings.kokoro_voices_path)

    def synthesize(self, text: str, *, voice: str, language: str) -> tuple[np.ndarray, int]:
        if self._k is None:
            self.load()
        lang_code = _LANG_CODES.get(language)
        if lang_code is None:
            raise ValueError(
                f"Lingua '{language}' non supportata da Kokoro. "
                f"Valori validi: {sorted(_LANG_CODES)}"
            )
        # speed SEMPRE 1.0: il cambio di velocità è centralizzato in audio.py (atempo).
        samples, sr = self._k.create(text, voice=voice, speed=1.0, lang=lang_code)
        return samples.astype(np.float32), sr

    def list_voices(self) -> list[str]:
        # Id nativi letti dal file voices (npz): non richiede il modello onnx.
        if not self._settings.kokoro_voices_path:
            return []
        try:
            with np.load(self._settings.kokoro_voices_path, allow_pickle=True) as data:
                return sorted(data.files)
        except (OSError, ValueError) as e:
            logger.warning("File voci Kokoro non leggibile (%s): []", e)
            return []

    def list_voice_files(self) -> list[str]:
        # Kokoro non usa file reference.
        return []
