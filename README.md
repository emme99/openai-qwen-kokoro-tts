# TTS locale OpenAI-compatible — Qwen3-TTS + Kokoro-82M

> **⚠️ Disclaimer** — Progetto **sperimentale**, realizzato con l'ausilio di strumenti di intelligenza artificiale e fornito **"così com'è"**, senza garanzie di alcun tipo, esplicite o implicite. L'autore **non si assume alcuna responsabilità** per l'utilizzo di questo software né per eventuali danni, diretti o indiretti, derivanti dal suo impiego: l'uso avviene sotto l'esclusiva responsabilità di chi lo utilizza. Clona voci solo con il consenso degli interessati e nel rispetto delle leggi applicabili.

> **English?** See [README-EN.md](README-EN.md).

Servizio TTS **interamente locale** con API OpenAI-compatible (`/v1/audio/speech`), due engine
intercambiabili da `.env` e un registro voci unificato. Pensato come drop-in per
[tutor-local](https://github.com/emme99/tutor-local) e per qualunque client OpenAI-compatible.

- **Qwen3-TTS** (0.6B, voice cloning da file reference, MPS/CUDA/CPU)
- **Kokoro-82M** (via `kokoro-onnx`, CPU, voci native, modello int8 di default)

> ⚠️ **Disclaimer**: progetto sperimentale, realizzato con l'ausilio di strumenti AI, fornito "as is"
> senza alcuna garanzia. Non clonare voci senza consenso né per scopi ingannevoli (deepfake, frodi).
> Il modello può produrre artefatti o allucinazioni: è uno strumento di ricerca/sviluppo.

## Caratteristiche

- **Drop-in OpenAI**: `POST /v1/audio/speech`, `GET /v1/voices`, `GET /health`.
- **Due engine, un'API**: `TTS_ENGINE=qwen|kokoro`; il client non cambia.
- **Registro voci unificato** (`voices.toml`): nome logico stabile → binding per engine
  (file reference per Qwen, voce nativa per Kokoro). Il client usa solo i nomi logici.
- **Velocità reale**: `speed` 0.25–4.0 via catena `atempo` (pitch preservato), identica tra engine.
- **Voice cloning** (Qwen): reference audio 5–10 s, cache dei prompt su disco.
- **Concorrenza sicura**: inferenza serializzata da lock + `asyncio.to_thread` (event loop libero).
- **Preload** all'avvio (`PRELOAD=true`), header di diagnostica (`X-Engine`, `X-Voice`,
  `X-Voice-Fallback`, `X-Device`, `X-Process-Time-Ms`).
- **Console web** di valutazione (`web-app/`): profili multi-endpoint, A/B blind, bench con gate, storia.
- **Test senza modelli** (pytest + ruff; node:test per la web-app) e **bench CLI** con gate.
- **Local-first**: bind `127.0.0.1`, nessuna autenticazione, nessun dato verso il cloud.

## Engine a confronto

| | Qwen3-TTS | Kokoro-82M |
|---|---|---|
| Backend | `qwen-tts` + PyTorch | `kokoro-onnx` (onnxruntime) |
| Device | MPS (sperimentale) / CUDA / CPU | CPU |
| Voci | cloning da `voices/*.wav` | native (`if_sara`, `am_adam`, …) |
| Modello | `Qwen3-TTS-12Hz-0.6B-Base` (~1,2 GB) | `kokoro-v1.0.int8.onnx` (~80 MB) |
| RAM indicativa | ~3–4 GB (float32) | ~0,5 GB |
| dtype | **float32 obbligatorio** (float16 rotto) | n/a (int8/fp32) |
| Punti di forza | cloning, flessibilità | velocità, leggerezza, zero torch |

## Requisiti

- Python 3.11+ (baseline verificata: **3.13 su MacBook M3 Max**)
- `ffmpeg` (per mp3 e per il cambio di velocità via atempo): `brew install ffmpeg`
- Node ≥ 18 per la console web (`web-app/`)
- macOS (Apple Silicon) o Linux; CUDA opzionale per Qwen

## Avvio rapido

### Kokoro (percorso più leggero, consigliato per partire)
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt          # API + Kokoro (niente torch)
python scripts/download_kokoro.py        # scarica int8 + voices in models/
cp .env.example .env                     # imposta TTS_ENGINE=kokoro
python app.py                            # http://127.0.0.1:5050
```
Per il modello fp32: `python scripts/download_kokoro.py --full` e
`KOKORO_MODEL_PATH=./models/kokoro-v1.0.onnx`.

### Qwen3-TTS (voice cloning)
```bash
pip install -r requirements.txt -r requirements-qwen.txt   # aggiunge torch
cp .env.example .env                     # TTS_ENGINE=qwen, DEVICE=mps, DTYPE=float32
python app.py                            # il modello si scarica al primo avvio
```
Metti i reference audio in `voices/` (es. `alloy.wav`, `ash.wav`, 5–10 s, con consenso).

### Prova
```bash
curl -X POST http://127.0.0.1:5050/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"Ciao, come stai?","voice":"alloy","language":"it","speed":0.7,"response_format":"mp3"}' \
  --output out.mp3

curl http://127.0.0.1:5050/v1/voices
curl http://127.0.0.1:5050/health
```

## API

### `POST /v1/audio/speech`
| Parametro | Default | Note |
|---|---|---|
| `input` | — | testo (obbligatorio, ≤ `MAX_INPUT_CHARS`) |
| `voice` | `default` | nome logico, id nativo Kokoro o file Qwen (vedi sotto) |
| `language` | `DEFAULT_LANGUAGE` | **solo `it` / `en`** a livello API |
| `speed` | `1.0` | 0.25–4.0; atempo, pitch preservato |
| `response_format` | `mp3` | `mp3` o `wav` |
| `model` | `qwen3-tts` | formalità di protocollo (ignorato) |

Header di risposta: `X-Engine`, `X-Voice` (binding risolto), `X-Voice-Fallback`
(`cross-lingual` o `language-default`, solo se scattato), `X-Device`, `X-Process-Time-Ms`.

Errori: `400` input vuoto/troppo lungo, speed fuori range, lingua non supportata, voce o default
non risolvibili (con elenco voci disponibili); `500` errori dell'engine. **Mai fallback rumorosi.**

### `GET /v1/voices`
`{engine, defaults:{it,en}, registry:[{name,language,qwen,kokoro}], native:[...], files:[...]}`

### `GET /health`
`{status, engine, device, model_loaded, defaults:{it,en}}`

## Voci: registro unificato

Il client usa **nomi logici stabili**; `voices.toml` mappa il binding per engine:
```toml
[alloy]
language = "it"
qwen = "voices/alloy.wav"
kokoro = "if_sara"

[ash]
language = "en"
qwen = "voices/ash.wav"
kokoro = "am_adam"
```
Ordine di risoluzione (`voices.py`, funzione pura):
1. `language` mancante → `DEFAULT_LANGUAGE`; non supportata → `400`.
2. Voce nel registro → binding dell'engine attivo; binding mancante → default per lingua (warning).
3. Fuori registro: Qwen → file legacy `voices/{voce}.wav`; Kokoro → id nativo (passthrough)
   **solo se la lingua del prefisso coincide** (`if_`/`im_`→it, `af_`/`am_`/`bf_`/`bm_`→en).
4. Non risolvibile / `default` / vuoto → default per lingua (`VOICE_IT`/`VOICE_EN`); se fallisce → `400`.
5. Politica lingua: la lingua richiesta vince sempre. Qwen è cross-lingual (reference kept,
   `X-Voice-Fallback: cross-lingual`); Kokoro è language-bound (sostituisce col default,
   `X-Voice-Fallback: language-default`).

**Aggiungere una voce clonata (Qwen):** metti `voices/mia_voce.wav`, aggiungi una sezione in
`voices.toml` con `qwen = "voices/mia_voce.wav"` (e opzionalmente `kokoro`).
**Kokoro:** usa gli id nativi da `/v1/voices` (nessun file da aggiungere).

## Velocità

`speed` ∈ [0.25, 4.0]. Gli engine sintetizzano **sempre a 1.0**; il cambio avviene in `audio.py`
con una catena di stadi `atempo` (ciascuno in [0.5, 2.0]), es. `0.3 → [0.5, 0.6]`, `2.5 → [2.0, 1.25]`.
Pitch preservato, comportamento identico tra engine. Richiede `ffmpeg`.

## Configurazione

Precedenza: **env > `config.json` (deprecato) > default**. Fonte di verità: `.env.example`.

| Variabile | Default | Significato |
|---|---|---|
| `TTS_ENGINE` | `qwen` | `qwen` \| `kokoro` |
| `HOST` / `PORT` | `127.0.0.1` / `5050` | bind (solo localhost) |
| `PRELOAD` | `true` | carica il modello all'avvio |
| `DEFAULT_LANGUAGE` | `it` | lingua se non specificata |
| `VOICE_IT` / `VOICE_EN` | `alloy` / `ash` | nomi logici di default |
| `MAX_INPUT_CHARS` | `2000` | guardrail lunghezza input |
| `VOICES_REGISTRY` | `voices.toml` | percorso registro |
| `DEVICE` / `DTYPE` | `mps` / `float32` | Qwen: **non usare float16** |
| `MODEL_PATH` | `./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base` | checkpoint Qwen |
| `FLASH_ATTN` | `false` | Qwen, se flash-attn installato |
| `KOKORO_MODEL_PATH` | `./models/kokoro-v1.0.int8.onnx` | int8 (~2× più veloce su CPU) |
| `KOKORO_VOICES_PATH` | `./models/voices-v1.0.bin` | voci native Kokoro |

## Console web (`web-app/`)

Console di valutazione generica per endpoint TTS OpenAI-compatible (non conosce gli engine:
conosce **profili**). Vanilla JS + Express, nessun build step.
```bash
cd web-app && npm install && npm start   # http://127.0.0.1:3000
npm test                                 # test dei moduli puri
```
- **Sintesi**: profilo, voce (discovery o libera), lingua, velocità (preset 0.3/0.7/1.0), formato;
  metriche (servizio/client/durata/RTF/bytes/voce risolta), p50/p95 per profilo·device.
- **Confronto A/B**: due profili, sintesi sequenziale, etichette casuali, voto blind, tally, export.
- **Bench**: set frasi, warmup scartato, gate (qwen 2000 ms, kokoro 800 ms), impronta SHA-256, export.
- **Storia**: persistente, filtri, replay/rigenera, export CSV/JSON.

Per l'A/B tra engine: due istanze del servizio (`TTS_ENGINE=qwen PORT=5050` e
`TTS_ENGINE=kokoro PORT=5052`), oppure una sola istanza riavviata con engine diverso.
Dettagli in `web-app/README.md`.

## Benchmark CLI

```bash
python scripts/bench_tts.py --engine qwen,kokoro --speed 1.0
```
Avvia/ferma il servizio per ogni engine, attende `/health`, misura cold start + 3 run × 10 frasi
(5 it, 5 en), p50/p95 server e client, RSS. **Gate**: qwen p50 ≤ 2.0 s, kokoro p50 ≤ 0.8 s
(exit 1 se falliti; `--no-gate` per ignorare). Report in `results/report.md` con impronta.
Opzioni: `--port`, `--python`, `--speed`.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # nessun modello, niente torch richiesto
ruff check .
cd web-app && npm test       # node:test, moduli puri
```
CI: sposta `web-app/ci-webapp.yml` in `.github/workflows/` (workflow non ancora attivo).

## Docker

Su Mac un container è una VM Linux: **niente MPS**, si va di CPU. La compose è pensata per
`DEVICE=cpu`. Kokoro (CPU) gira bene in container; Qwen in CPU è lento. **Su Apple Silicon
conviene il nativo** (`python app.py`, MPS). Docker ha senso su Linux (CPU/CUDA) o per un server
domestico. Il servizio TTS non va esposto in rete (nessuna autenticazione).

## Sicurezza e privacy

- Bind `127.0.0.1` di default, nessuna auth: **non esporre la porta**.
- Audio e testo restano locali; i modelli si scaricano una volta (HuggingFace / release kokoro-onnx).
- Voice cloning: usa reference solo con consenso. Tratta `voices/` come dati personali.

## Troubleshooting

| Sintomo | Rimedio |
|---|---|
| Probabilità invalide / audio rotto (Qwen) | `DTYPE=float32` (float16 non supportato) |
| MPS instabile/lento | `DEVICE=cpu` come fallback; MPS è sperimentale |
| Prima richiesta molto lenta | `PRELOAD=true`; il cold start include il load del modello |
| `ffmpeg non trovato` | `brew install ffmpeg` (mp3 e atempo) |
| `400` voce non risolvibile | controlla `/v1/voices`; aggiungi binding in `voices.toml` |
| `400` lingua non supportata | solo `it`/`en` a livello API |
| Fallback `language-default` inatteso | voce Kokoro di lingua diversa dalla richiesta (prefisso) |
| RAM insufficiente | un solo engine/modello alla volta; Kokoro è ~0,5 GB |
| Porta occupata | cambia `PORT` (o la porta della console web) |

## Layout del progetto

```
app.py            rotte FastAPI, lock, lifespan/preload, header
config.py         Settings (env > config.json > default)
audio.py          atempo + encoding WAV/MP3 (percorso unico)
voices.py         resolver puro + registro; voices.toml
engines/          base.py, qwen.py, kokoro.py (import pesanti in load())
service.py        QwenTTSService (cloning, cache prompt)
errors.py         VoiceNotFound
scripts/          bench_tts.py, download_kokoro.py
tests/            pytest (API, audio, voices, engines, settings, guardrail)
web-app/          console di valutazione (Express + vanilla JS)
voices/           reference audio Qwen (.wav)
models/           checkpoint (gitignored)
```

## Integrazione con tutor-local

Drop-in: in tutor-local imposta `TTS_BASE_URL=http://127.0.0.1:5050/v1`,
`TTS_VOICE_IT=alloy`, `TTS_VOICE_EN=ash`. Cambiando `TTS_ENGINE` nel servizio,
**tutor-local non cambia una riga**: i nomi logici restano validi su entrambi gli engine.

## Riferimenti

- [Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base)
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) · [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)
- [FastAPI](https://fastapi.tiangolo.com/) · [ffmpeg](https://ffmpeg.org/)

## Licenza

MIT — vedi [LICENSE](LICENSE). Copyright (c) 2026.