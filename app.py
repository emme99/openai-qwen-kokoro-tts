import logging
from time import perf_counter
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import Settings
from service import QwenTTSService, VoiceNotFound

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qwen-tts-api")

app = FastAPI(title="Qwen3 TTS OpenAI API")

# Settings: precedenza env > config.json (deprecato) > default
settings = Settings.load()

# Initialize Service
logger.info(
    f"Initializing service with config: model={settings.model_path}, device={settings.device}, "
    f"dtype={settings.dtype}, flash_attn={settings.flash_attn}, lang={settings.default_language}"
)
tts_service = QwenTTSService(
    model_path=settings.model_path,
    device=settings.device,
    dtype=settings.dtype,
    flash_attn=settings.flash_attn
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
        # Use request param if provided, otherwise default from settings
        language = request.language or settings.default_language
        
        started_at = perf_counter()
        audio_buffer = tts_service.synthesize(
            request.input, 
            voice_ref_path=request.voice, 
            lang=language,
            format=request.response_format
        )
        process_time_ms = (perf_counter() - started_at) * 1000
        
        media_type = "audio/wav"
        filename = "speech.wav"
        
        if request.response_format == "mp3":
            media_type = "audio/mpeg"
            filename = "speech.mp3"
        
        # Return audio stream
        return StreamingResponse(
            audio_buffer, 
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Device": tts_service.device,
                "X-Process-Time-Ms": f"{process_time_ms:.1f}",
            }
        )


    except VoiceNotFound as e:
        # Voce non risolvibile: errore esplicito con elenco voci disponibili.
        logger.warning(f"Voice not found: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating speech: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    uvicorn.run(app, host=settings.host, port=settings.port)
