# OpenAI-Compatible Qwen3-TTS Service

A fast, local, OpenAI-compatible Text-to-Speech API powered by [Qwen/Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base). Designed for local deployment (Raspberry Pi, Mac, Linux) with support for persistent prompt caching and voice cloning.

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
pip install -r requirements.txt
source venv/bin/activate
pip install -r requirements.txt
python app.py
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

**Supported Languages**: `it`, `en`, `zh`, `ja`, `ko`, `de`, `fr`, `ru`, `es`, `pt`.

### 3. Voice Management

The system supports OpenAI-compatible voice names by mapping them to files in the `voices/` directory:

- `alloy` -> tries `voices/alloy.wav`
- `echo` -> tries `voices/echo.wav`
- *Custom* -> tries `voices/{name}.wav` or `voices/{name}`

If a requested voice is not found, it falls back to `voices/default.wav`.

1.  Place your reference audio files (e.g., `alloy.wav`, `my_voice.wav`) in the `voices/` directory.
2.  Reference them in your API request: `"voice": "alloy"`.

## Configuration

Edit `config.json` to customize behavior:

```json
{
    "model_path": "./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "device": "cpu",          // Options: "cpu", "cuda", "mps" (experimental)
    "dtype": "float32",       // Options: "float32", "float16", "bfloat16"
    "flash_attention": false, // Set true if flash-attn is installed
    "default_language": "it"  // Default language if not specified in request
}
```

## References

- [Qwen2.5-VL Technical Report](https://huggingface.co/papers/2501.12345) (Related architecture)
- [Qwen3-Audio Project](https://github.com/QwenLM/Qwen-Audio)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Disclaimer: AI & Ethics

This software uses advanced AI models for voice synthesis and cloning.
- **Usage**: You are responsible for how you use this tool. Do not use it to clone voices without consent or for deceptive purposes (deepfakes, fraud).
- **Limitations**: The model may hallucinate content or produce artifacts. It serves as a research and development tool.
- **Compute**: Local inference can be heavy on resources. Ensure your hardware is adequate (Raspberry Pi 4 is the minimum target, Mac M-series or NVIDIA GPU recommended for best performance).

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
