"""Benchmark TTS con gate (stile tutor-local).

Per ogni engine richiesto avvia il servizio (TTS_ENGINE=<engine>), attende
/health, misura:
  - cold start: prima richiesta (include eventuale lazy load del modello);
  - p50/p95 a caldo: 3 run per frase, latenza server (X-Process-Time-Ms)
    e latenza client-side;
  - RSS del processo server (prima/dopo).

Gate (exit 1 se falliti): qwen p50 <= 2.0 s, kokoro p50 <= 0.8 s.
Salva results/report.md con l'impronta (engine + modello + frasi + speed).

Uso:
    python scripts/bench_tts.py [--engine qwen,kokoro] [--speed 1.0]
                                [--port 5050] [--no-gate] [--python ./venv/bin/python]
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# 10 frasi (~15 parole): 5 it + 5 en.
SENTENCES = [
    ("it", "Oggi andremo a esplorare insieme i fondamenti della programmazione in Python."),
    ("it", "La fotosintesi clorofilliana trasforma la luce solare in energia chimica per le piante."),
    ("it", "Per risolvere l'equazione dobbiamo isolare la variabile incognita sul lato sinistro."),
    ("it", "Il Rinascimento italiano ha rivoluzionato arte, scienza e pensiero europeo per secoli."),
    ("it", "Ricorda di bere almeno due litri di acqua al giorno per stare bene."),
    ("en", "The quick brown fox jumps over the lazy dog near the riverbank at dawn."),
    ("en", "Machine learning models require large amounts of labeled data to generalize well."),
    ("en", "Photosynthesis converts sunlight into chemical energy that plants use to grow."),
    ("en", "The committee will review the proposal and share its findings by next Friday."),
    ("en", "Always test your code on the edge cases before shipping it to production."),
]

GATES = {"qwen": 2.0, "kokoro": 0.8}  # p50 server-side in secondi
RUNS = 3


def percentile(values: list[float], pct: float) -> float:
    """Percentile con interpolazione lineare (come numpy.percentile)."""
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def rss_mb(pid: int) -> float | None:
    """RSS del processo in MB (macOS: ps -o rss=)."""
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return int(out) / 1024 if out else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def wait_health(base_url: str, timeout: float = 180.0) -> dict:
    """Attende /health (il preload del modello può richiedere minuti)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return json.loads(urllib.request.urlopen(f"{base_url}/health", timeout=3).read())
        except OSError:
            time.sleep(1)
    raise TimeoutError(f"Servizio non pronto su {base_url} dopo {timeout:.0f} s")


def request(base_url: str, text: str, voice: str, language: str, speed: float) -> dict:
    """POST /v1/audio/speech; ritorna latenze e metadati."""
    payload = json.dumps(
        {"input": text, "voice": voice, "language": language, "speed": speed,
         "response_format": "mp3"}
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/v1/audio/speech",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read()
        client_ms = (time.perf_counter() - t0) * 1000
        server_ms = float(resp.headers.get("X-Process-Time-Ms", client_ms))
        return {
            "server_ms": server_ms,
            "client_ms": client_ms,
            "bytes": len(body),
            "voice": resp.headers.get("X-Voice"),
            "fallback": resp.headers.get("X-Voice-Fallback"),
        }


def bench_engine(base_url: str, pid: int, speed: float) -> dict:
    """Cold start + 3 run per frase verso un servizio gia' in esecuzione."""
    rss_before = rss_mb(pid)

    # Cold start: prima richiesta (include eventuale lazy load del modello).
    lang, text = SENTENCES[0]
    cold = request(base_url, text, "default", lang, speed)

    per_sentence = []
    for lang, text in SENTENCES:
        runs = [request(base_url, text, "default", lang, speed) for _ in range(RUNS)]
        per_sentence.append({
            "language": lang,
            "text": text,
            "server_ms": [r["server_ms"] for r in runs],
            "client_ms": [r["client_ms"] for r in runs],
            "voice": runs[0]["voice"],
            "fallback": runs[0]["fallback"],
        })

    rss_after = rss_mb(pid)
    all_server = [ms for s in per_sentence for ms in s["server_ms"]]
    all_client = [ms for s in per_sentence for ms in s["client_ms"]]
    return {
        "cold_start_ms": cold["server_ms"],
        "cold_start_client_ms": cold["client_ms"],
        "per_sentence": per_sentence,
        "p50_server_ms": percentile(all_server, 50),
        "p95_server_ms": percentile(all_server, 95),
        "p50_client_ms": percentile(all_client, 50),
        "p95_client_ms": percentile(all_client, 95),
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
    }


def run_engine(engine: str, port: int, speed: float, python: str) -> dict:
    """Avvia il servizio con l'engine, esegue il benchmark, lo ferma."""
    base_url = f"http://127.0.0.1:{port}"
    env = dict(os.environ, TTS_ENGINE=engine, PORT=str(port), PRELOAD="true")
    proc = subprocess.Popen(
        [python, "app.py"], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        health = wait_health(base_url)
        if health.get("engine") != engine:
            raise RuntimeError(f"Engine atteso '{engine}', servizio risponde '{health.get('engine')}'")
        print(f"  servizio pronto (model_loaded={health.get('model_loaded')})")
        result = bench_engine(base_url, proc.pid, speed)
        result["engine"] = engine
        return result
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def fmt_ms(v: float) -> str:
    return f"{v:,.0f} ms" if v == v else "n/a"


def write_report(path: Path, speed: float, results: list[dict]) -> None:
    lines = [
        "# Report benchmark TTS",
        "",
        f"- Data: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Speed: {speed}",
        f"- Run per frase: {RUNS}",
        f"- Frasi: {len(SENTENCES)} ({sum(1 for lang, _ in SENTENCES if lang == 'it')} it, "
        f"{sum(1 for lang, _ in SENTENCES if lang == 'en')} en, ~15 parole)",
        "",
        "## Impronta frasi",
        "",
    ]
    for lang, text in SENTENCES:
        lines.append(f"- **{lang}**: {text}")
    lines.append("")

    for r in results:
        gate = GATES.get(r["engine"])
        lines += [
            f"## Engine: {r['engine']}",
            "",
            f"- Cold start (server): {fmt_ms(r['cold_start_ms'])} "
            f"(client: {fmt_ms(r['cold_start_client_ms'])})",
            f"- **p50 server: {fmt_ms(r['p50_server_ms'])}** | p95 server: {fmt_ms(r['p95_server_ms'])}",
            f"- p50 client: {fmt_ms(r['p50_client_ms'])} | p95 client: {fmt_ms(r['p95_client_ms'])}",
        ]
        if r["rss_before_mb"] is not None and r["rss_after_mb"] is not None:
            lines.append(f"- RSS server: {r['rss_before_mb']:.0f} MB -> {r['rss_after_mb']:.0f} MB")
        lines += [
            "",
            "| Lingua | Voce | p50 server | p95 server | p50 client |",
            "|--------|------|-----------|-----------|-----------|",
        ]
        for s in r["per_sentence"]:
            lines.append(
                f"| {s['language']} | {s['voice']} | {fmt_ms(percentile(s['server_ms'], 50))} "
                f"| {fmt_ms(percentile(s['server_ms'], 95))} "
                f"| {fmt_ms(percentile(s['client_ms'], 50))} |"
            )
        if gate is not None:
            ok = r["p50_server_ms"] / 1000 <= gate
            lines += ["", f"**Gate p50 <= {gate:.1f} s: {'PASS' if ok else 'FAIL'}**"]
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", default="qwen,kokoro",
                        help="Engine da testare, separati da virgola (default: qwen,kokoro)")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--python", default=sys.executable,
                        help="Interprete per avviare il servizio (default: quello corrente)")
    parser.add_argument("--no-gate", action="store_true",
                        help="Non fallisce (exit 0) se un gate non e' soddisfatto")
    args = parser.parse_args()

    engines = [e.strip() for e in args.engine.split(",") if e.strip()]
    results = []
    for engine in engines:
        print(f"=== Benchmark {engine} ===")
        r = run_engine(engine, args.port, args.speed, args.python)
        results.append(r)
        print(f"  cold start: {fmt_ms(r['cold_start_ms'])}")
        print(f"  p50 server: {fmt_ms(r['p50_server_ms'])} | p95: {fmt_ms(r['p95_server_ms'])}")

    report = Path("results/report.md")
    write_report(report, args.speed, results)
    print(f"\nReport: {report}")

    failed = []
    for r in results:
        gate = GATES.get(r["engine"])
        if gate is not None and r["p50_server_ms"] / 1000 > gate:
            failed.append(f"{r['engine']}: p50 {r['p50_server_ms'] / 1000:.2f} s > {gate:.1f} s")
    if failed:
        print("GATE FALLITI:", *failed, sep="\n  - ")
        return 1 if not args.no_gate else 0
    print("Tutti i gate soddisfatti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
