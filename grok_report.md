

Project Plan: Implementing Qwen3-TTS-12Hz-0.6B as a Local-First OpenAI-Compatible TTS Service on Raspberry Pi 4B for Home Assistant Integration
Overview
This project aims to deploy Qwen3-TTS-12Hz-0.6B (a multilingual TTS model with strong Italian support) as a local-first service on a Raspberry Pi 4B (4GB RAM, CPU-only) using Python and Docker. The service will be compatible with the OpenAI API format, specifically for generating audio responses to short phrases (e.g., 5-20 words) in Italian. It will integrate with Home Assistant's Assist feature to replace the current Edge TTS setup, addressing issues with Italian language quality in other systems.
Key goals:

Offline operation (local-first) after initial setup.
Low-latency inference for short phrases, despite hardware constraints.
Focus on Italian voice quality and voice cloning if needed.
Containerized deployment for portability and ease of management.

Expected challenges: High CPU inference latency (RTF >10x on RPi), memory constraints (4GB RAM limit), and no GPU acceleration.
Prerequisites
Hardware

Raspberry Pi 4B with 4GB RAM.
MicroSD card (at least 32GB, preferably with Raspberry Pi OS Lite 64-bit for ARM64).
Stable power supply and cooling (e.g., heatsink/fan) to prevent throttling during inference.
Network access for initial setup (downloads), but runtime is offline.

Software

Raspberry Pi OS (64-bit recommended for ARM64 compatibility).
Docker (install via sudo apt install docker.io or official script).
Python 3.12+ (for Qwen-TTS package).
Git for cloning repositories.
Home Assistant instance (core or supervised) with Assist configured to use custom TTS endpoints.

Dependencies

Qwen3-TTS model: Download from Hugging Face (Qwen/Qwen3-TTS-12Hz-0.6B-Base, ~2.5GB).
Python packages: qwen-tts, torch (CPU version), fastapi, uvicorn, soundfile, huggingface-hub.
Optional: ONNX Runtime for potential CPU optimizations.

Step-by-Step Implementation Plan
Phase 1: Environment Setup (1-2 hours)

Install OS and Docker on Raspberry Pi:
Flash Raspberry Pi OS 64-bit to SD card.
Boot and update: sudo apt update && sudo apt upgrade.
Install Docker: curl -sSL https://get.docker.com | sh.
Add user to docker group: sudo usermod -aG docker $USER (reboot).

Test Hardware Resources:
Monitor memory/CPU: Install htop (sudo apt install htop).
Ensure no heavy background processes; aim for <1GB idle RAM usage.


Phase 2: Model Download and Testing (2-4 hours)

Download Qwen3-TTS Model:
Install Hugging Face CLI: pip install huggingface-hub.
Download offline: huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-Base --local-dir /path/to/models.
Verify size and integrity.

Local Python Testing:
Create virtual env: python -m venv tts_env && source tts_env/bin/activate.
Install packages: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu (CPU wheels).
Install pip install qwen-tts soundfile.
Test script:Pythonfrom qwen_tts import Qwen3TTSModel
import soundfile as sf

model = Qwen3TTSModel.from_pretrained("/path/to/models", device="cpu")
text = "Ciao, questo è un test breve in italiano."
audio = model.synthesize(text, lang="it")  # Adjust for voice cloning if needed
sf.write("output.wav", audio, samplerate=24000)
Run and measure time/memory: Expect 10-30s for short phrase; optimize if OOM occurs (e.g., use torch.float16 if supported).

Handle Voice Cloning (Optional):
If custom Italian voice needed: Provide reference audio/text in synthesis call.
Test: audio = model.synthesize(text, ref_audio="ref.wav", ref_text="Riferimento italiano.", lang="it").


Phase 3: Build OpenAI-Compatible API (3-5 hours)

Choose/Implement Server:
Use existing repo (e.g., fork/clone from GitHub: search for "Qwen3-TTS OpenAI API wrapper").
Or build custom with FastAPI:
Install pip install fastapi uvicorn.
Sample app.py:Pythonfrom fastapi import FastAPI
from qwen_tts import Qwen3TTSModel
import io
from fastapi.responses import StreamingResponse

app = FastAPI()
model = Qwen3TTSModel.from_pretrained("/path/to/models", device="cpu")

@app.post("/v1/audio/speech")
async def tts(request: dict):  # Parse OpenAI-like JSON: {"input": text, "voice": optional}
    text = request["input"]
    audio = model.synthesize(text, lang="it")  # Add voice cloning params
    buf = io.BytesIO()
    sf.write(buf, audio, samplerate=24000, format="WAV")
    buf.seek(0)
    return StreamingResponse(buf, media_type="audio/wav")

Run: uvicorn app:app --host 0.0.0.0 --port 8000.

Dockerize the Service:
Create Dockerfile (ARM64 compatible):textFROM python:3.12-slim-bookworm arm64

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /models  # Mount model dir

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
requirements.txt: List packages (torch CPU, qwen-tts, etc.).
Build: docker build -t qwen-tts-service ..
Run: docker run -d -p 8000:8000 -v /path/to/models:/models qwen-tts-service.

Test API Locally:
Use curl: curl -X POST http://localhost:8000/v1/audio/speech -H "Content-Type: application/json" -d '{"input": "Test frase italiana."}' --output test.wav.
Verify audio quality and latency.


Phase 4: Integrate with Home Assistant (1-3 hours)

Configure Custom TTS in HA:
Install TTS add-on or use core TTS integration.
Add custom provider: Edit configuration.yaml:texttts:
  - platform: rest
    name: Qwen TTS
    base_url: http://<rpi-ip>:8000/v1/audio/speech
    service_name: POST
    fields:
      input: "{{ message }}"
Set as default for Assist: In HA settings, select Qwen TTS for voice responses.

Test Integration:
Trigger Assist with short Italian phrases (e.g., "Che ore sono?").
Monitor RPi resources; ensure no crashes.


Phase 5: Optimizations and Monitoring (Ongoing)

Performance Tweaks:
Quantization: Explore ONNX export (torch.onnx.export) and ONNX Runtime for faster CPU inference.
Batch size: Limit to single short phrases.
Overclock RPi (if safe) or add swap file (but avoid for speed).
Fallback: If too slow, hybrid with Edge TTS for non-Italian.

Error Handling:
Add API retries/queues for concurrent requests.
Logging: Use logging in Python; monitor with Docker logs.

Security:
Expose API only locally (firewall); use auth if networked.


Potential Issues and Mitigations

Memory OOM: Reduce dtype to float16; unload model when idle.
High Latency: Limit to <10-word phrases; inform users of delays.
Model Quality: Fine-tune if Italian accents need adjustment (advanced).
ARM64 Compatibility: Test all packages; fallback to source builds if wheels fail.
Power/Heat: Monitor temps; add cooling