import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from service import QwenTTSService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qwen-tts-api")

app = FastAPI(title="Qwen3 TTS OpenAI API")

# Configuration
import json

# Configuration loading
CONFIG_FILE = "config.json"
config = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)

# Defaults or overrides
MODEL_PATH = os.getenv("MODEL_PATH", config.get("model_path", "./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base"))
DEVICE = os.getenv("DEVICE", config.get("device", "cpu"))
DTYPE = os.getenv("DTYPE", config.get("dtype", "float32"))
FLASH_ATTN = os.getenv("FLASH_ATTN", str(config.get("flash_attention", False))).lower() == "true"

# Initialize Service
logger.info(f"Initializing service with config: model={MODEL_PATH}, device={DEVICE}, dtype={DTYPE}, flash_attn={FLASH_ATTN}")
tts_service = QwenTTSService(
    model_path=MODEL_PATH, 
    device=DEVICE,
    dtype=DTYPE,
    flash_attn=FLASH_ATTN
)

# OpenAI-compatible Request Model
class SpeechRequest(BaseModel):
    model: str = "qwen3-tts"
    input: str
    voice: Optional[str] = "default"
    response_format: Optional[str] = "wav" # We mainly support mp3/wav, but we'll output wav for now
    speed: Optional[float] = 1.0

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Qwen TTS Service...")
    # Optional: Preload model on startup
    # tts_service.load_model() 

@app.post("/v1/audio/speech")
async def generate_speech(request: SpeechRequest):
    """
    Generates audio from the input text.
    """
    try:
        if not request.input:
            raise HTTPException(status_code=400, detail="Input text is required.")

        # Determine language? defaulting to Italian as per user goal, 
        # but could be inferred or passed in voice param.
        # For this PoC, we stick to Italian.
        language = "it" 
        
        audio_buffer = tts_service.synthesize(request.input, voice_ref_path=request.voice, lang=language)
        
        # Return audio stream
        return StreamingResponse(
            audio_buffer, 
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=speech.wav"}
        )

    except Exception as e:
        logger.error(f"Error generating speech: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}
