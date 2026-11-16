"""Test API con FakeEngine: errori, headers, lock, speed."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import app as app_module


def _post(client, payload):
    return client.post("/v1/audio/speech", json=payload)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine"] == "fake"
    assert body["device"] == "fake"
    assert body["model_loaded"] is False
    assert body["defaults"] == {"it": "alloy", "en": "ash"}


def test_preload_calls_load(monkeypatch):
    """Con PRELOAD=true il lifespan chiama engine.load() all'avvio."""
    from tests.conftest import FakeEngine

    fake = FakeEngine()
    loaded = []
    fake.load = lambda: loaded.append(True)

    monkeypatch.setattr(app_module, "engine", fake)
    monkeypatch.setattr(app_module.settings, "preload", True)

    with TestClient(app_module.app):
        pass

    assert loaded == [True]


def test_no_preload_skips_load(monkeypatch):
    """Con PRELOAD=false il modello non viene caricato all'avvio."""
    from tests.conftest import FakeEngine

    fake = FakeEngine()
    loaded = []
    fake.load = lambda: loaded.append(True)

    monkeypatch.setattr(app_module, "engine", fake)
    monkeypatch.setattr(app_module.settings, "preload", False)

    with TestClient(app_module.app):
        pass

    assert loaded == []


def test_speech_returns_wav(client):
    r = _post(client, {"input": "ciao", "voice": "alloy", "language": "it", "response_format": "wav"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert "X-Process-Time-Ms" in r.headers
    assert len(r.content) > 1000


def test_speech_returns_mp3(client):
    r = _post(client, {"input": "ciao", "voice": "alloy", "language": "it", "response_format": "mp3"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"


def test_empty_input_400(client):
    r = _post(client, {"input": "", "voice": "alloy"})
    assert r.status_code == 400


@pytest.mark.parametrize("speed", [0.1, 5.0, -1.0])
def test_speed_out_of_range_400(client, speed):
    r = _post(client, {"input": "ciao", "voice": "alloy", "speed": speed})
    assert r.status_code == 400
    assert "speed" in r.json()["detail"]


def test_speed_in_range_ok(client):
    for speed in (0.25, 0.7, 1.0, 4.0):
        r = _post(client, {"input": "ciao", "voice": "alloy", "speed": speed})
        assert r.status_code == 200, f"speed={speed}"


def test_voice_not_found_400(client, monkeypatch):
    # Engine che alza VoiceNotFound
    from errors import VoiceNotFound

    def boom(text, *, voice, language):
        raise VoiceNotFound(voice, ["alloy", "ash"])

    monkeypatch.setattr(app_module.engine, "synthesize", boom)
    r = _post(client, {"input": "ciao", "voice": "inesistente"})
    assert r.status_code == 400
    assert "alloy" in r.json()["detail"]


def test_engine_error_500(client, monkeypatch):
    def boom(text, *, voice, language):
        raise RuntimeError("modello rotto")

    monkeypatch.setattr(app_module.engine, "synthesize", boom)
    r = _post(client, {"input": "ciao", "voice": "alloy"})
    assert r.status_code == 500


# --- Concorrenza: lock serializza, /health resta responsive ---

@pytest.fixture
def swap_engine():
    """Sostituisce app.engine e lo restaura dopo il test."""
    original = app_module.engine

    def _swap(fake):
        app_module.engine = fake
        return fake

    yield _swap
    app_module.engine = original


def test_concurrent_requests_serialized(swap_engine):
    """Due POST concorrenti con sleep 0.5 durano ~1.0s totali (serializzati)."""
    from tests.conftest import FakeEngine

    fake = swap_engine(FakeEngine(sleep=0.5))

    async def run():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            start = time.perf_counter()
            r1, r2 = await asyncio.gather(
                ac.post("/v1/audio/speech", json={"input": "a", "voice": "alloy"}),
                ac.post("/v1/audio/speech", json={"input": "b", "voice": "alloy"}),
            )
            elapsed = time.perf_counter() - start
            return r1, r2, elapsed

    r1, r2, elapsed = asyncio.run(run())
    assert r1.status_code == 200 and r2.status_code == 200
    # Serializzati: ~1.0s (2 x 0.5), non ~0.5s (paralleli). Tolleranza per overhead.
    assert elapsed >= 0.9, f"richieste non serializzate: {elapsed:.2f}s"
    assert fake.calls == 2


def test_health_responsive_during_synthesis(swap_engine):
    """/health risponde in <50ms mentre una sintesi è in corso."""
    from tests.conftest import FakeEngine

    swap_engine(FakeEngine(sleep=1.0))

    async def run():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            synth = asyncio.create_task(
                ac.post("/v1/audio/speech", json={"input": "a", "voice": "alloy"})
            )
            await asyncio.sleep(0.2)  # la sintesi è in corso
            start = time.perf_counter()
            health = await ac.get("/health")
            health_ms = (time.perf_counter() - start) * 1000
            await synth
            return health, health_ms

    health, health_ms = asyncio.run(run())
    assert health.status_code == 200
    assert health_ms < 50, f"/health lento durante sintesi: {health_ms:.1f}ms"
