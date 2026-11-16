import asyncio
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import audio
from config import Settings
from engines import make_engine
from errors import VoiceNotFound

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qwen-tts-api")

# Settings: precedenza env > config.json (deprecato) > default
settings = Settings.load()

# Engine selezionato da TTS_ENGINE (modello non ancora caricato: vedi lifespan).
engine = make_engine(settings)

logger.info(
    f"Initializing TTS service: engine={engine.name}, device={settings.device}, "
    f"lang={settings.default_language}"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload del modello all'avvio se PRELOAD=true (in thread, non blocca l'event loop)."""
    if settings.preload:
        logger.info("PRELOAD=true: carico il modello all'avvio...")
        await asyncio.to_thread(engine.load)
        logger.info("Modello precaricato.")
    yield


app = FastAPI(title="Qwen3 TTS OpenAI API", lifespan=lifespan)

# Lock globale: l'inferenza è bloccante e va serializzata (un solo modello in RAM).
_inference_lock = asyncio.Lock()

# OpenAI-compatible Request Model
class SpeechRequest(BaseModel):
    model: str = "qwen3-tts"
    input: str
    voice: Optional[str] = "default"
    language: Optional[str] = None 
    response_format: Optional[str] = "mp3" 
    speed: Optional[float] = 1.0

@app.post("/v1/audio/speech")
async def generate_speech(request: SpeechRequest):
    """
    Generates audio from the input text.
    """
    try:
        if not request.input:
            raise HTTPException(status_code=400, detail="Input text is required.")

        # Guardrail: input troppo lungo -> 400
        if len(request.input) > settings.max_input_chars:
            raise HTTPException(
                status_code=400,
                detail=f"Input troppo lungo: {len(request.input)} caratteri "
                       f"(max {settings.max_input_chars})",
            )

        # Validazione speed: fuori range -> 400
        speed = request.speed if request.speed is not None else 1.0
        if not (audio.SPEED_MIN <= speed <= audio.SPEED_MAX):
            raise HTTPException(
                status_code=400,
                detail=f"speed deve essere in [{audio.SPEED_MIN}, {audio.SPEED_MAX}], ricevuto {speed}",
            )

        # Determine language
        # Use request param if provided, otherwise default from settings
        language = request.language or settings.default_language

        started_at = perf_counter()
        # L'engine ritorna (samples float32, sample_rate); speed e formato sono
        # centralizzati in audio.py. Inferenza in thread separato sotto lock:
        # serializza le richieste concorrenti senza bloccare l'event loop
        # (pattern identico a tutor-local/backend/app/providers/stt.py).
        async with _inference_lock:
            samples, sample_rate = await asyncio.to_thread(
                engine.synthesize,
                request.input,
                voice=request.voice,
                language=language,
            )

        # Percorso unico di rendering (atempo + encoding) in audio.py
        audio_buffer, media_type, filename = audio.render(
            samples, sample_rate, speed, request.response_format
        )

        process_time_ms = (perf_counter() - started_at) * 1000

        # Return audio stream (lista di chunk: audio_buffer è bytes)
        return StreamingResponse(
            [audio_buffer],
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Engine": engine.name,
                "X-Device": getattr(engine, "device", settings.device),
                "X-Process-Time-Ms": f"{process_time_ms:.1f}",
            }
        )


    except VoiceNotFound as e:
        # Voce non risolvibile: errore esplicito con elenco voci disponibili.
        logger.warning(f"Voice not found: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # Le HTTPException già costruite (400 validazione, ecc.) passano invariate.
        raise
    except Exception as e:
        logger.error(f"Error generating speech: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "engine": engine.name,
        "device": getattr(engine, "device", settings.device),
        "model_loaded": getattr(engine, "model_loaded", False),
        "defaults": {"it": settings.voice_it, "en": settings.voice_en},
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    uvicorn.run(app, host=settings.host, port=settings.port)
