# Console TTS — valutazione OpenAI-compatible

Evoluzione della web-app da "Qwen3-TTS Tester" a console di test/valutazione per **qualsiasi**
servizio TTS OpenAI-compatible: Qwen3-TTS, Kokoro-82M, il servizio macOS `say`, altri.
Vanilla JS (ES modules) + CSS puro + Express. Nessun build step, nessuna UI library.

## Requisiti
- Node >= 18 (fetch nativo lato server). Unica dipendenza runtime: `express`.
- Uno o più servizi TTS OpenAI-compatible raggiungibili (vedi profili).

## Avvio
    npm install
    cp .env.example .env   # opzionale
    npm start              # http://127.0.0.1:3000
    npm test               # test dei moduli puri (nessun servizio richiesto)

## Configurazione (.env)
| Variabile | Default | Significato |
|---|---|---|
| PORT | 3000 | porta della console |
| HOST | 127.0.0.1 | bind (solo localhost di default) |
| ALLOWED_HOSTS | 127.0.0.1,localhost | host consentiti come target del proxy |
| ALLOW_ANY_HOST | false | true = consenti qualsiasi host http/https (endpoint generici/cloud) |
| TIMEOUT_MS | 120000 | timeout verso il servizio TTS |

Il proxy inoltra `speed`, `model`, `apiKey` e tutti gli header `X-*` del servizio (come `X-TTS-*`).
`speed` è validato lato proxy (0.25–4.0); l'effetto reale dipende dal servizio (vedi piano 1, T1.1 atempo).

## Profili
La console non conosce gli engine: conosce **endpoint**. Seed: qwen@5050, kokoro@5052, say@5051.
CRUD nel pannello "Gestisci profili" (tab Sintesi). Ogni profilo: nome, baseUrl, model, apiKey?, voci default IT/EN.
Discovery voci via `GET /v1/voices` con adapter per tre forme (unificata, mapping macOS, assente → input libero).

## Tab
- **Sintesi**: profilo, voce (discovery o libera), lingua, velocità (preset 0.3/0.7/1.0), formato, model, testo.
  Metriche: tempo servizio, totale client, durata audio, RTF, dimensione, voce risolta; banner fallback; p50/p95 per profilo·device.
- **Confronto A/B**: due profili, stesso testo, sintesi sequenziale (pacing 300 ms), etichette A/B casuali,
  voto A/B/pari + nota, reveal, tally, export JSON/MD. I nomi sono nascosti finché non voti.
- **Bench**: set `phrases.json` (10 frasi it/en), warmup scartato, repeats × frasi × profili, pacing,
  gate configurabili (default qwen 2000 ms, kokoro 800 ms), p50/p95/RTF, export report.md + JSON con impronta SHA-256.
- **Storia**: persistente (localStorage, ≤200 righe), filtri profilo/device, replay (ultimi 10 blob) e rigenera, export CSV/JSON.

## A/B tra engine: due istanze del servizio
Istanza 1: `TTS_ENGINE=qwen PORT=5050 PRELOAD=true`.
Istanza 2: `TTS_ENGINE=kokoro PORT=5052 PRELOAD=true KOKORO_MODEL_PATH=... KOKORO_VOICES_PATH=...`.
RAM ~4,5 GB totali. Con lo stretch F6 del piano 1 (model come override engine) basta una sola istanza.
Grazie al registro voci del piano 1, `alloy`/`ash` sono la stessa voce logica sui due engine → confronto equo.

## Note
- `phrases.json` è in `public/`; per condividerlo col bench CLI (`scripts/bench_tts.py`, piano 1 T5.2)
  puntare lo stesso file o copiarlo in `bench/phrases.json` nella root del repo.
- CI: spostare `ci-webapp.yml` in `.github/workflows/`.
- Sicurezza: bind localhost, allowlist host, niente CORS (same-origin). Endpoint non locale → avviso in UI.
- Dipendenze rispetto all'originale: rimosse `axios` e `cors` (fetch nativo + same-origin). `npm install` rigenera il lock.
