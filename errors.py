"""Errori di dominio del servizio TTS (modulo leggero, senza dipendenze pesanti)."""

from __future__ import annotations


class VoiceNotFound(Exception):
    """Nessuna voce risolvibile per la richiesta.

    Il messaggio contiene l'elenco delle voci disponibili, così il client
    riceve un errore esplicito (HTTP 400) invece di un fallback rumoroso.
    """

    def __init__(self, requested: str, available: list[str]):
        self.requested = requested
        self.available = available
        super().__init__(
            f"Voce '{requested}' non trovata. Voci disponibili: {', '.join(available) or '(nessuna)'}"
        )
