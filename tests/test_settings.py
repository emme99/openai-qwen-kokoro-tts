"""Test sulla precedenza delle Settings: env > config.json > default."""

import json

from config import Settings


def test_defaults_when_no_env_no_config(tmp_path):
    s = Settings.load(env={}, config_json_path=tmp_path / "missing.json")
    assert s.tts_engine == "qwen"
    assert s.host == "127.0.0.1"
    assert s.port == 5050
    assert s.preload is True
    assert s.default_language == "it"
    assert s.voice_it == "alloy"
    assert s.voice_en == "ash"
    assert s.max_input_chars == 2000
    assert s.device == "mps"
    assert s.dtype == "float32"
    assert s.flash_attn is False


def test_config_json_used_when_no_env(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"port": 6000, "device": "cpu", "default_language": "en"}))
    s = Settings.load(env={}, config_json_path=cfg)
    assert s.port == 6000
    assert s.device == "cpu"
    assert s.default_language == "en"
    # i campi non in config.json restano al default
    assert s.host == "127.0.0.1"


def test_env_overrides_config_json(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"port": 6000, "device": "cpu"}))
    s = Settings.load(env={"PORT": "7000"}, config_json_path=cfg)
    assert s.port == 7000
    # device non in env -> config.json
    assert s.device == "cpu"


def test_env_bool_parsing(tmp_path):
    s = Settings.load(env={"PRELOAD": "false", "FLASH_ATTN": "1"}, config_json_path=tmp_path / "x")
    assert s.preload is False
    assert s.flash_attn is True


def test_empty_env_value_falls_back_to_config(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"port": 6000}))
    s = Settings.load(env={"PORT": ""}, config_json_path=cfg)
    assert s.port == 6000
