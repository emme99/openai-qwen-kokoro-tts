"""Test T3.1: resolver voci puro (tutti i rami del §3)."""

import pytest

from voices import VoiceResolutionError, load_registry, native_voice_language, resolve_voice

REGISTRY = {
    "alloy": {"language": "it", "qwen": "voices/alloy.wav", "kokoro": "if_sara"},
    "ash": {"language": "en", "qwen": "voices/ash.wav", "kokoro": "am_adam"},
    "nova": {"language": "en", "qwen": "voices/nova.wav", "kokoro": "af_heart"},
    "sage": {"language": "en", "qwen": "voices/sage.wav", "kokoro": "bf_emma"},
}
FILES = ["alloy.wav", "ash.wav", "nova.wav", "sage.wav", "custom.wav"]
NATIVE = ["if_sara", "am_adam", "af_heart", "bf_emma", "af_bella"]
DEFAULTS = {"it": "alloy", "en": "ash"}


def _resolve(voice, language, engine, **kw):
    return resolve_voice(
        voice, language, engine, REGISTRY, FILES, NATIVE, DEFAULTS,
        default_language="it", **kw,
    )


# --- 1. Lingua ---

def test_language_missing_uses_default_language():
    r = _resolve("alloy", None, "qwen")
    assert r.language == "it"
    assert r.binding == "voices/alloy.wav"


def test_language_not_in_map_raises_400():
    with pytest.raises(VoiceResolutionError) as exc:
        _resolve("alloy", "fr", "qwen")
    assert "fr" in str(exc.value)
    assert "it" in str(exc.value) and "en" in str(exc.value)


# --- 2. Registro hit ---

def test_registry_hit_qwen():
    r = _resolve("alloy", "it", "qwen")
    assert r.binding == "voices/alloy.wav"
    assert r.fallback is None


def test_registry_hit_kokoro():
    r = _resolve("alloy", "it", "kokoro")
    assert r.binding == "if_sara"
    assert r.fallback is None


def test_registry_binding_missing_falls_back_to_default():
    # nova senza binding kokoro -> default en (ash) -> am_adam
    reg = {
        "nova": {"language": "en", "qwen": "voices/nova.wav"},
        "ash": {"language": "en", "qwen": "voices/ash.wav", "kokoro": "am_adam"},
        "alloy": {"language": "it", "qwen": "voices/alloy.wav", "kokoro": "if_sara"},
    }
    r = resolve_voice("nova", "en", "kokoro", reg, FILES, NATIVE, DEFAULTS, default_language="it")
    assert r.binding == "am_adam"
    assert r.fallback == "language-default"


# --- 3. Fuori registro ---

def test_qwen_legacy_file():
    r = _resolve("custom", "it", "qwen")
    assert r.binding == "custom.wav"
    assert r.fallback is None


def test_kokoro_native_passthrough():
    r = _resolve("af_bella", "en", "kokoro")
    assert r.binding == "af_bella"
    assert r.fallback is None


def test_kokoro_native_passthrough_italian():
    r = _resolve("if_sara", "it", "kokoro")
    assert r.binding == "if_sara"
    assert r.fallback is None


def test_kokoro_native_language_mismatch_falls_back():
    # if_sara (it) richiesta in inglese -> default en (ash) -> am_adam
    r = _resolve("if_sara", "en", "kokoro")
    assert r.binding == "am_adam"
    assert r.fallback == "language-default"


def test_kokoro_native_unknown_prefix_falls_back():
    # jf_alpha (giapponese) non è usabile per it/en -> default
    reg = {
        "alloy": {"language": "it", "kokoro": "if_sara"},
        "ash": {"language": "en", "kokoro": "am_adam"},
    }
    r = resolve_voice(
        "jf_alpha", "it", "kokoro", reg, FILES, ["jf_alpha"], DEFAULTS,
        default_language="it",
    )
    assert r.binding == "if_sara"
    assert r.fallback == "language-default"


# --- Prefisso -> lingua (voci native Kokoro) ---

def test_native_voice_language_prefixes():
    assert native_voice_language("if_sara") == "it"
    assert native_voice_language("im_nicola") == "it"
    assert native_voice_language("af_heart") == "en"
    assert native_voice_language("am_adam") == "en"
    assert native_voice_language("bf_emma") == "en"
    assert native_voice_language("bm_lewis") == "en"
    assert native_voice_language("jf_alpha") is None
    assert native_voice_language("zf_xiaobei") is None


def test_qwen_unknown_name_falls_back_to_default():
    r = _resolve("inesistente", "it", "qwen")
    assert r.binding == "voices/alloy.wav"
    assert r.fallback == "language-default"


# --- 4. Default / vuoto ---

def test_voice_default_uses_language_default():
    r = _resolve("default", "en", "qwen")
    assert r.binding == "voices/ash.wav"
    assert r.fallback is None


def test_voice_empty_uses_language_default():
    r = _resolve(None, "it", "kokoro")
    assert r.binding == "if_sara"
    assert r.fallback is None


def test_default_unresolvable_raises_400():
    # default en = ash, ma ash non ha binding kokoro e non è nativo
    reg = {"ash": {"language": "en"}}
    with pytest.raises(VoiceResolutionError) as exc:
        resolve_voice("default", "en", "kokoro", reg, [], [], DEFAULTS, default_language="it")
    assert "ash" in str(exc.value)
    assert exc.value.available  # elenco voci non vuoto


# --- 5. Politica lingua ---

def test_qwen_cross_lingual_keeps_reference():
    # ash (en) richiesta in italiano: qwen fa cloning cross-lingual
    r = _resolve("ash", "it", "qwen")
    assert r.binding == "voices/ash.wav"
    assert r.fallback == "cross-lingual"


def test_kokoro_cross_lingual_replaces_with_default():
    # ash (en) richiesta in italiano: kokoro sostituisce col default it
    r = _resolve("ash", "it", "kokoro")
    assert r.binding == "if_sara"
    assert r.fallback == "language-default"


# --- load_registry ---

def test_load_registry_from_file(tmp_path):
    p = tmp_path / "voices.toml"
    p.write_text('[alloy]\nlanguage = "it"\nqwen = "voices/alloy.wav"\nkokoro = "if_sara"\n')
    reg = load_registry(p)
    assert reg["alloy"]["kokoro"] == "if_sara"


def test_load_registry_missing_file(tmp_path):
    assert load_registry(tmp_path / "assente.toml") == {}


def test_repo_registry_loads():
    """Il voices.toml del repo è valido e contiene le voci base."""
    from pathlib import Path

    reg = load_registry(Path(__file__).parent.parent / "voices.toml")
    for name in ("alloy", "ash", "nova", "sage"):
        assert name in reg
        assert reg[name]["language"] in ("it", "en")
