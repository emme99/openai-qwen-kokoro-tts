# Local OpenAI-compatible TTS — Qwen3-TTS + Kokoro-82M

> **⚠️ Disclaimer** — An **experimental** project, built with the assistance of AI tools and provided **"as is"**, without warranties of any kind, express or implied. The author **assumes no responsibility or liability** for the use of this software or for any direct or indirect damages arising from it: use is entirely at your own risk. Clone voices only with the consent of the individuals involved and in compliance with applicable laws.

> **Italiano?** Vedi [README.md](README.md).

A fully **local** Text-to-Speech service with an OpenAI-compatible API (`/v1/audio/speech`),
two interchangeable engines selected via `.env`, and a unified voice registry. Designed as a
drop-in for [tutor-local](https://github.com/emme99/tutor-local) and any OpenAI-compatible client.

- **Qwen3-TTS** (0.6B, voice cloning from reference files, MPS/CUDA/CPU)
- **Kokoro-82M** (via `kokoro-onnx`, CPU, built-in voices, int8 model by default)

> ⚠️ **Disclaimer**: experimental project, built with AI assistance, provided "as is" without any
> warranty. Do not clone voices without consent or for deceptive purposes (deepfakes, fraud).
> The model may produce artifacts or hallucinations: it is a research/development tool.

## Features

- **OpenAI drop-in**: `POST /v1/audio/speech`, `GET /v1/voices`, `GET /health`.
- **Two engines, one API**: `TTS_ENGINE=qwen|kokoro`; the client never changes.
- **Unified voice registry** (`voices.toml`): stable logical name → per-engine binding
  (reference file for Qwen, built-in voice for Kokoro). Clients only use logical names.
- **Real speed control**: `speed` 0.25–4.0 via an `atempo` chain (pitch preserved), identical across engines.
- **Voice cloning** (Qwen): 5–10 s reference audio, on-disk prompt caching.
- **Safe concurrency**: inference serialized by a lock + `asyncio.to_thread` (event loop stays free).
- **Startup preload** (`PRELOAD=true`), diagnostic headers (`X-Engine`, `X-Voice`,
  `X-Voice-Fallback`, `X-Device`, `X-Process-Time-Ms`).
- **Web evaluation console** (`web-app/`): multi-endpoint profiles, blind A/B, gated bench, history.
- **Model-free tests** (pytest + ruff; node:test for the web app) and a **gated bench CLI**.
- **Local-first**: binds `127.0.0.1`, no auth, no data leaves the machine.

## Engines compared

| | Qwen3-TTS | Kokoro-82M |
|---|---|---|
| Backend | `qwen-tts` + PyTorch | `kokoro-onnx` (onnxruntime) |
| Device | MPS (experimental) / CUDA / CPU | CPU |
| Voices | cloning from `voices/*.wav` | built-in (`if_sara`, `am_adam`, …) |
| Model | `Qwen3-TTS-12Hz-0.6B-Base` (~1.2 GB) | `kokoro-v1.0.int8.onnx` (~80 MB) |
| Approx. RAM | ~3–4 GB (float32) | ~0.5 GB |
| dtype | **float32 required** (float16 broken) | n/a (int8/fp32) |
| Strengths | cloning, flexibility | speed, lightness, no torch |

## Requirements

- Python 3.11+ (verified baseline: **3.13 on MacBook M3 Max**)
- `ffmpeg` (for mp3 and for speed changes via atempo): `brew install ffmpeg`
- Node ≥ 18 for the web console (`web-app/`)
- macOS (Apple Silicon) or Linux; CUDA optional for Qwen

## Quick start

### Kokoro (lightest path, recommended to get going)
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt          # API + Kokoro (no torch)
python scripts/download_kokoro.py        # downloads int8 + voices into models/
cp .env.example .env                     # set TTS_ENGINE=kokoro
python app.py                            # http://127.0.0.1:5050
```
For the fp32 model: `python scripts/download_kokoro.py --full` and
`KOKORO_MODEL_PATH=./models/kokoro-v1.0.onnx`.

### Qwen3-TTS (voice cloning)
```bash
pip install -r requirements.txt -r requirements-qwen.txt   # adds torch
cp .env.example .env                     # TTS_ENGINE=qwen, DEVICE=mps, DTYPE=float32
python app.py                            # model auto-downloads on first run
```
Place reference audio in `voices/` (e.g. `alloy.wav`, `ash.wav`, 5–10 s, with consent).

### Try it
```bash
curl -X POST http://127.0.0.1:5050/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"Hello, how are you?","voice":"ash","language":"en","speed":0.7,"response_format":"mp3"}' \
  --output out.mp3

curl http://127.0.0.1:5050/v1/voices
curl http://127.0.0.1:5050/health
```

## API

### `POST /v1/audio/speech`
| Parameter | Default | Notes |
|---|---|---|
| `input` | — | text (required, ≤ `MAX_INPUT_CHARS`) |
| `voice` | `default` | logical name, Kokoro native id, or Qwen file (see below) |
| `language` | `DEFAULT_LANGUAGE` | **only `it` / `en`** at the API level |
| `speed` | `1.0` | 0.25–4.0; atempo, pitch preserved |
| `response_format` | `mp3` | `mp3` or `wav` |
| `model` | `qwen3-tts` | protocol formality (ignored) |

Response headers: `X-Engine`, `X-Voice` (resolved binding), `X-Voice-Fallback`
(`cross-lingual` or `language-default`, only when triggered), `X-Device`, `X-Process-Time-Ms`.

Errors: `400` empty/too-long input, speed out of range, unsupported language, unresolvable voice or
default (with the list of available voices); `500` engine errors. **Never noisy fallbacks.**

### `GET /v1/voices`
`{engine, defaults:{it,en}, registry:[{name,language,qwen,kokoro}], native:[...], files:[...]}`

### `GET /health`
`{status, engine, device, model_loaded, defaults:{it,en}}`

## Voices: unified registry

Clients use **stable logical names**; `voices.toml` maps the per-engine binding:
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
Resolution order (`voices.py`, pure function):
1. Missing `language` → `DEFAULT_LANGUAGE`; unsupported → `400`.
2. Voice in registry → active engine's binding; missing binding → per-language default (warning).
3. Outside registry: Qwen → legacy file `voices/{voice}.wav`; Kokoro → native id (passthrough)
   **only if the prefix language matches** (`if_`/`im_`→it, `af_`/`am_`/`bf_`/`bm_`→en).
4. Unresolvable / `default` / empty → per-language default (`VOICE_IT`/`VOICE_EN`); if that fails → `400`.
5. Language policy: the requested language always wins. Qwen is cross-lingual (reference kept,
   `X-Voice-Fallback: cross-lingual`); Kokoro is language-bound (replaced with the default,
   `X-Voice-Fallback: language-default`).

**Add a cloned voice (Qwen):** drop `voices/my_voice.wav`, add a section in `voices.toml` with
`qwen = "voices/my_voice.wav"` (and optionally `kokoro`).
**Kokoro:** use native ids from `/v1/voices` (no file to add).

## Speed

`speed` ∈ [0.25, 4.0]. Engines always synthesize at **1.0**; the change happens in `audio.py`
via a chain of `atempo` stages (each in [0.5, 2.0]), e.g. `0.3 → [0.5, 0.6]`, `2.5 → [2.0, 1.25]`.
Pitch preserved, identical behavior across engines. Requires `ffmpeg`.

## Configuration

Precedence: **env > `config.json` (deprecated) > defaults**. Source of truth: `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `TTS_ENGINE` | `qwen` | `qwen` \| `kokoro` |
| `HOST` / `PORT` | `127.0.0.1