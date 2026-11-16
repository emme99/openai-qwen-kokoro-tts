"""Wrapper Qwen3-TTS: incapsula service.QwenTTSService nel contratto TTSEngine.

Gli import pesanti (torch, qwen_tts, via service) avvengono dentro `load()`,
mai a livello di modulo: così questo file è importabile anche senza torch
installato (necessario per la suite di test in CI).
"""

from __future__ import annotations

import logging

import numpy as np

from config import Settings

logger = logging.getLogger(__name__)


class QwenEngine:
    """Engine Qwen3-TTS (voice cloning da file reference)."""

    name = "qwen"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._service = None  # istanziato dentro load()

    @property
    def device(self) -> str:
        return self._settings.device

    @property
    def model_loaded(self) -> bool:
        return self._service is not None and self._service.model is not None

    def load(self) -> None:
        if self._service is not None:
            return
        # Import pesante: trascina torch/qwen_tts. Solo qui, non a livello modulo.
        from service import QwenTTSService

        logger.info(
            "Carico QwenEngine: model=%s device=%s dtype=%s",
            self._settings.model_path,
            self._settings.device,
            self._settings.dtype,
        )
        self._service = QwenTTSService(
            model_path=self._settings.model_path,
            device=self._settings.device,
            dtype=self._settings.dtype,
            flash_attn=self._settings.flash_attn,
        )
        self._service.load_model()

    def synthesize(self, text: str, *, voice: str, language: str) -> tuple[np.ndarray, int]:
        if self._service is None:
            self.load()
        # L'engine produce sempre WAV; speed/formato sono centralizzati in audio.py.
        wav_buffer = self._service.synthesize(
            text, voice_ref_path=voice, lang=language, format="wav"
        )
        import io

        import soundfile as sf

        samples, sr = sf.read(io.BytesIO(wav_buffer.getvalue()), dtype="float32")
        return samples, sr

    def list_voices(self) -> list[str]:
        # I file reference in voices/ non richiedono il modello caricato.
        from service import list_voice_files

        return list_voice_files()
