"""Factory degli engine: seleziona l'implementazione da `TTS_ENGINE`."""

from __future__ import annotations

import logging

from config import Settings
from engines.base import TTSEngine

logger = logging.getLogger(__name__)


def make_engine(settings: Settings) -> TTSEngine:
    """Costruisce l'engine indicato da `settings.tts_engine`.

    Il modello NON viene caricato qui: `load()` è chiamato dal lifespan
    (se PRELOAD=true) o alla prima richiesta (lazy).
    """
    engine = settings.tts_engine.lower()
    if engine == "qwen":
        from engines.qwen import QwenEngine

        return QwenEngine(settings)
    if engine == "kokoro":
        from engines.kokoro import KokoroEngine

        return KokoroEngine(settings)
    raise ValueError(
        f"TTS_ENGINE sconosciuto: '{settings.tts_engine}'. Valori validi: qwen, kokoro"
    )
