"""Impostazioni del servizio TTS.

Precedenza: variabili d'ambiente > config.json (deprecato) > default.
`config.json` continua a funzionare ma è deprecato: se viene usato per
risolvere un valore, viene emesso un warning una sola volta.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Mappa campo Settings -> chiave in config.json (nomenclatura legacy)
_CONFIG_JSON_KEYS = {
    "model_path": "model_path",
    "device": "device",
    "dtype": "dtype",
    "flash_attn": "flash_attention",
    "default_language": "default_language",
    "port": "port",
}

_config_json_warned = False


def _load_config_json(path: str | Path = "config.json") -> dict:
    """Legge config.json se esiste; ritorna {} altrimenti."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("config.json illeggibile (%s): ignorato", e)
        return {}


def _env_bool(value, default: bool) -> bool:
    """Converte un valore env (str) o config.json (bool/str) in bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    """Parametri del servizio, risolti da env > config.json > default."""

    # --- Generici ---
    tts_engine: str = "qwen"
    host: str = "127.0.0.1"
    port: int = 5050
    preload: bool = True
    default_language: str = "it"
    voice_it: str = "alloy"
    voice_en: str = "ash"
    max_input_chars: int = 2000
    voices_registry: str = "voices.toml"

    # --- Qwen3-TTS ---
    model_path: str = "./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    device: str = "mps"
    dtype: str = "float32"
    flash_attn: bool = False

    # --- Kokoro-82M (onnx, CPU) ---
    kokoro_model_path: str = "./models/kokoro-v1.0.onnx"
    kokoro_voices_path: str = "./models/voices-v1.0.bin"

    # config.json letto (per test e deprecazione)
    _config_json: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(
        cls,
        env: dict | None = None,
        config_json_path: str | Path = "config.json",
    ) -> "Settings":
        """Costruisce le Settings applicando la precedenza env > config.json > default."""
        env = os.environ if env is None else env
        cfg = _load_config_json(config_json_path)

        def pick(field_name: str, env_key: str, default, cast=None):
            """Precedenza: env > config.json > default."""
            global _config_json_warned
            if env_key in env and env.get(env_key) not in (None, ""):
                value = env[env_key]
            elif field_name in _CONFIG_JSON_KEYS and _CONFIG_JSON_KEYS[field_name] in cfg:
                value = cfg[_CONFIG_JSON_KEYS[field_name]]
                if not _config_json_warned:
                    logger.warning(
                        "config.json è deprecato: usa le variabili d'ambiente "
                        "(vedi .env.example). Valori legacy in uso: %s",
                        sorted(k for k in _CONFIG_JSON_KEYS.values() if k in cfg),
                    )
                    _config_json_warned = True
            else:
                value = default
            if cast is not None and value is not None:
                value = cast(value)
            return value

        return cls(
            tts_engine=pick("tts_engine", "TTS_ENGINE", "qwen"),
            host=pick("host", "HOST", "127.0.0.1"),
            port=pick("port", "PORT", 5050, cast=int),
            preload=pick("preload", "PRELOAD", True, cast=lambda v: _env_bool(v, True)),
            default_language=pick("default_language", "DEFAULT_LANGUAGE", "it"),
            voice_it=pick("voice_it", "VOICE_IT", "alloy"),
            voice_en=pick("voice_en", "VOICE_EN", "ash"),
            max_input_chars=pick("max_input_chars", "MAX_INPUT_CHARS", 2000, cast=int),
            voices_registry=pick("voices_registry", "VOICES_REGISTRY", "voices.toml"),
            model_path=pick("model_path", "MODEL_PATH", "./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base"),
            device=pick("device", "DEVICE", "mps"),
            dtype=pick("dtype", "DTYPE", "float32"),
            flash_attn=pick(
                "flash_attn", "FLASH_ATTN", False, cast=lambda v: _env_bool(v, False)
            ),
            kokoro_model_path=pick(
                "kokoro_model_path", "KOKORO_MODEL_PATH", "./models/kokoro-v1.0.onnx"
            ),
            kokoro_voices_path=pick(
                "kokoro_voices_path", "KOKORO_VOICES_PATH", "./models/voices-v1.0.bin"
            ),
            _config_json=cfg,
        )
