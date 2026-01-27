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
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", config.get("default_language", "it"))

# Initialize Service
logger.info(f"Initializing service with config: model={MODEL_PATH}, device={DEVICE}, dtype={DTYPE}, flash_attn={FLASH_ATTN}, lang={DEFAULT_LANGUAGE}")
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
    language: Optional[str] = None 
    response_format: Optional[str] = "mp3" 
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

        # Determine language
        # Use request param if provided, otherwise default from config
        language = request.language or DEFAULT_LANGUAGE
        
        audio_buffer = tts_service.synthesize(
            request.input, 
            voice_ref_path=request.voice, 
            lang=language,
            format=request.response_format
        )
        
        media_type = "audio/wav"
        filename = "speech.wav"
        
        if request.response_format == "mp3":
            media_type = "audio/mpeg"
            filename = "speech.mp3"
        
        # Return audio stream
        return StreamingResponse(
            audio_buffer, 
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


    except Exception as e:
        logger.error(f"Error generating speech: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = config.get("port", 8000)
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
