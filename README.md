# OpenAI-Compatible Qwen3-TTS Service

A fast, local, OpenAI-compatible Text-to-Speech API powered by [Qwen/Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base). Designed for local deployment on Mac and Linux with support for persistent prompt caching and voice cloning.

## Features

- **OpenAI API Compatibility**: Drop-in replacement for OpenAI's `/v1/audio/speech` endpoint.
- **Voice Cloning**: Clone voices by simply providing a 5-10s reference audio file.
- **Persistent Caching**: Caches voice features to disk for faster subsequent inference.
- **Auto-Model Download**: Automatically fetches the model from HuggingFace on first run.
- **Hardware Acceleration**: Supports Apple Silicon (MPS - Experimental) and CUDA (via configuration).

## Quick Start

### 1. Installation

**Using Docker (Recommended)**
```bash
docker-compose up --build
```

**Using pure Docker**
```bash
# Build the image
docker build -t qwen-tts-service .

# Run the container (mounting models, voices, and config)
docker run -d \
  -p 5050:5050 \
  -v $(pwd)/models:/models \
  -v $(pwd)/voices:/app/voices \
  -v $(pwd)/config.json:/app/config.json \
  --name qwen-tts \
  qwen-tts-service
```

**Manual Setup**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt            # API + engine Kokoro (onnx, CPU)
pip install -r requirements-qwen.txt       # solo per l'engine Qwen (torch)
python app.py
```

For development/testing (no models, no torch needed):
```bash
pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
```

### 2. Usage

Generate speech using `curl`:

```bash
curl -X POST http://localhost:5050/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-tts",
    "input": "Ciao, come stai?",
    "voice": "alloy",
    "language": "it",
    "response_format": "mp3"
  }' \
  --output output.mp3
```

**Supported Formats**: `mp3` (default), `wav`.
**Note**: `mp3` support requires `ffmpeg` to be installed on the system.

**Supported Languages**: `it`, `en` (default per lingua configurabile in `.env`).

**Response headers**: `X-Engine` (engine attivo), `X-Voice` (binding risolto),
`X-Voice-Fallback` (solo se scattato: `cross-lingual` o `language-default`),
`X-Device`, `X-Process-Time-Ms`.

### 3. Voice Management

Voices are resolved through a unified registry (`voices.toml`): a stable logical
name maps to a per-engine binding, so clients don't need to know whether the
active engine uses reference files (Qwen) or built-in voices (Kokoro).

Resolution order:

1. `language` missing → `DEFAULT_LANGUAGE`; unsupported language → `400`.
2. `voice` in the registry → binding of the active engine; missing binding → step 4.
3. `voice` not in the registry: Qwen → legacy file `voices/{voice}.wav`;
   Kokoro → valid native voice id (passthrough), only when the voice's
   language (from its prefix: `if_`/`im_` → Italian, `af_`/`am_`/`bf_`/`bm_`
   → English) matches the requested language; otherwise step 4.
4. Unresolvable (or `voice="default"`/empty) → per-language default
   (`VOICE_IT`/`VOICE_EN`). If even that fails → `400` with the list of
   available voices. Never noise.
5. Language policy: the requested language always wins. Qwen cloning is
   cross-lingual (reference kept, `X-Voice-Fallback: cross-lingual`); Kokoro
   voices are language-bound (replaced with the language default,
   `X-Voice-Fallback: language-default`).

1.  Place your reference audio files (e.g., `alloy.wav`, `my_voice.wav`) in the `voices/` directory.
2.  Reference them in your API request: `"voice": "alloy"`.

Inspect the current voice setup with:

```bash
curl http://localhost:5050/v1/voices
```

Returns `{engine, defaults: {it, en}, registry: [...], native: [...], files: [...]}`.

## Configuration

Configuration is read from environment variables (see `.env.example`);
`config.json` is still honored for backward compatibility but deprecated
(a warning is logged once). Precedence: env > config.json > default.

```bash
MODEL_PATH=./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base
DEVICE=cpu            # Options: cpu, cuda, mps (experimental)
DTYPE=float32         # Options: float32, float16, bfloat16
FLASH_ATTN=false      # Set true if flash-attn is installed
DEFAULT_LANGUAGE=it   # Default language if not specified in request
VOICE_IT=alloy        # Default voice for Italian
VOICE_EN=ash          # Default voice for English
TTS_ENGINE=qwen       # Options: qwen, kokoro
PRELOAD=true          # Load the model at startup
```

On Apple Silicon, run the service natively with `python app.py` and set `device` to `mps` and `dtype` to `float32`. The Docker Compose configuration explicitly sets `DEVICE=cpu`, and a Docker container on macOS cannot access Apple's Metal/MPS backend. Keep `float32` for this model: `float16` produced invalid probabilities during local testing.

## References

- [Qwen2.5-VL Technical Report](https://huggingface.co/papers/2501.12345) (Related architecture)
- [Qwen3-Audio Project](https://github.com/QwenLM/Qwen-Audio)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Disclaimer: AI & Ethics

This software uses advanced AI models for voice synthesis and cloning.
- **Usage**: You are responsible for how you use this tool. Do not use it to clone voices without consent or for deceptive purposes (deepfakes, fraud).
- **Limitations**: The model may hallucinate content or produce artifacts. It serves as a research and development tool.
- **Compute**: Local inference is resource-intensive. A modern CPU or supported GPU is recommended.

## License

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
