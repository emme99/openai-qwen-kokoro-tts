"""Registro voci unificato + resolver puro (T3.1).

Il client usa nomi logici stabili (alloy, ash, ...); il binding per engine
vive in voices.toml. `resolve_voice` è una funzione PURA e deterministica:
nessun I/O, nessun torch — tutta la logica è testabile in CI.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Registro: {nome: {"language": str, "qwen": str, "kokoro": str, ...}}
Registry = dict[str, dict[str, str]]


class VoiceResolutionError(Exception):
    """Voce non risolvibile: 400 con elenco voci disponibili. Mai rumore."""

    def __init__(self, message: str, available: list[str]):
        super().__init__(message)
        self.available = available


@dataclass(frozen=True)
class ResolvedVoice:
    """Esito della risoluzione.

    fallback: None | "cross-lingual" (qwen, reference di altra lingua)
              | "language-default" (kokoro, sostituita col default della lingua)
    """

    binding: str
    fallback: str | None
    language: str


# Prefisso voce nativa Kokoro -> lingua (voices-v1.0.bin).
# i* = italiano, a*/b* = inglese; gli altri prefissi (jf_, zf_, ...) sono
# lingue non supportate dal servizio.
_NATIVE_PREFIX_LANG = {
    "if": "it",
    "im": "it",
    "af": "en",
    "am": "en",
    "bf": "en",
    "bm": "en",
}


def native_voice_language(voice: str) -> str | None:
    """Lingua di una voce nativa Kokoro dal prefisso (if_/im_ -> it, af_/am_/bf_/bm_ -> en).

    Ritorna None per prefissi sconosciuti (es. jf_, zf_): la voce non è
    usabile per le lingue del servizio.
    """
    prefix = voice.split("_", 1)[0]
    return _NATIVE_PREFIX_LANG.get(prefix)


def load_registry(path: str | Path) -> Registry:
    """Legge voices.toml (tomllib è stdlib). File assente -> registro vuoto."""
    p = Path(path)
    if not p.exists():
        logger.warning("Registro voci %s non trovato: registro vuoto", p)
        return {}
    with open(p, "rb") as f:
        data = tomllib.load(f)
    return {name: dict(entry) for name, entry in data.items()}


def _available(
    registry: Registry, files: list[str], native: list[str], defaults: dict[str, str]
) -> list[str]:
    """Elenco voci disponibili per i messaggi d'errore (deduplicato, ordinato)."""
    names = set(registry) | set(files) | set(native) | set(defaults.values())
    return sorted(names)


def _language_default(
    language: str,
    engine: str,
    registry: Registry,
    files: list[str],
    native: list[str],
    defaults: dict[str, str],
) -> str:
    """Default per lingua (passo 4): nome logico -> binding dell'engine."""
    default_name = defaults.get(language)
    if not default_name:
        raise VoiceResolutionError(
            f"Nessuna voce di default per la lingua '{language}'",
            _available(registry, files, native, defaults),
        )
    entry = registry.get(default_name)
    if entry and entry.get(engine):
        return entry[engine]
    # Compatibilità legacy: il default può puntare a un file qwen.
    if engine == "qwen" and f"{default_name}.wav" in files:
        return f"{default_name}.wav"
    if engine == "kokoro" and default_name in native:
        return default_name
    raise VoiceResolutionError(
        f"Voce di default '{default_name}' non risolvibile per l'engine '{engine}'",
        _available(registry, files, native, defaults),
    )


def resolve_voice(
    voice: str | None,
    language: str | None,
    engine: str,
    registry: Registry,
    files: list[str],
    native: list[str],
    defaults: dict[str, str],
    default_language: str | None = None,
) -> ResolvedVoice:
    """Risoluzione voce secondo l'ordine del §3 del piano.

    1. language mancante -> default_language; non in mappa -> VoiceResolutionError (400).
    2. voice nel registro -> binding dell'engine; binding mancante -> passo 4.
    3. voice fuori registro: qwen -> file legacy voices/{voice}.wav;
       kokoro -> id nativo valido (passthrough) solo se la lingua della voce
       (dal prefisso) coincide con quella richiesta, altrimenti default.
    4. Non risolvibile / "default" / vuoto -> default per lingua;
       se anche quello fallisce -> VoiceResolutionError. Mai rumore.
    5. Politica lingua: la lingua della richiesta vince sempre.
    """
    # 1. Lingua
    lang = language or default_language
    if lang is None or lang not in defaults:
        raise VoiceResolutionError(
            f"Lingua non supportata: '{language}'. Lingue disponibili: {sorted(defaults)}",
            _available(registry, files, native, defaults),
        )

    # 4 (anticipato): "default" / vuoto -> default per lingua
    if not voice or voice == "default":
        return ResolvedVoice(_language_default(lang, engine, registry, files, native, defaults), None, lang)

    # 2. Registro
    entry = registry.get(voice)
    if entry is not None:
        binding = entry.get(engine)
        if not binding:
            logger.warning(
                "Voce '%s' senza binding per l'engine '%s': uso il default per lingua",
                voice, engine,
            )
            return ResolvedVoice(
                _language_default(lang, engine, registry, files, native, defaults),
                "language-default", lang,
            )
        # 5. Politica lingua
        voice_lang = entry.get("language")
        if voice_lang and voice_lang != lang:
            if engine == "qwen":
                # Cloning cross-lingual: il reference resta valido.
                return ResolvedVoice(binding, "cross-lingual", lang)
            # Kokoro: le voci sono legate alla lingua -> default della lingua richiesta.
            return ResolvedVoice(
                _language_default(lang, engine, registry, files, native, defaults),
                "language-default", lang,
            )
        return ResolvedVoice(binding, None, lang)

    # 3. Fuori registro
    if engine == "qwen" and f"{voice}.wav" in files:
        return ResolvedVoice(f"{voice}.wav", None, lang)
    if engine == "kokoro" and voice in native:
        # Le voci Kokoro sono legate alla lingua: passthrough solo se la lingua
        # della voce coincide con quella richiesta (prefisso if_/im_ -> it,
        # af_/am_/bf_/bm_ -> en). Altrimenti -> default della lingua richiesta.
        voice_lang = native_voice_language(voice)
        if voice_lang == lang:
            return ResolvedVoice(voice, None, lang)
        logger.warning(
            "Voce nativa '%s' (%s) non compatibile con la lingua '%s': uso il default",
            voice, voice_lang or "sconosciuta", lang,
        )
        return ResolvedVoice(
            _language_default(lang, engine, registry, files, native, defaults),
            "language-default", lang,
        )

    # 4. Non risolvibile -> default per lingua
    logger.warning("Voce '%s' non risolvibile: uso il default per lingua '%s'", voice, lang)
    return ResolvedVoice(
        _language_default(lang, engine, registry, files, native, defaults),
        "language-default", lang,
    )
