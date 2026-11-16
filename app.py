import asyncio
import io
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Optional

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import audio
from config import Settings
from service import QwenTTSService, VoiceNotFound

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qwen-tts-api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload del modello all'avvio se PRELOAD=true (in thread, non blocca l'event loop)."""
    if settings.preload:
        logger.info("PRELOAD=true: carico il modello all'avvio...")
        await asyncio.to_thread(tts_service.load_model)
        logger.info("Modello precaricato.")
    yield


app = FastAPI(title="Qwen3 TTS OpenAI API", lifespan=lifespan)

# Lock globale: l'inferenza è bloccante e va serializzata (un solo modello in RAM).
_inference_lock = asyncio.Lock()

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
        # L'engine produce sempre WAV; speed e formato sono centralizzati in audio.py.
        # Inferenza in thread separato sotto lock: serializza le richieste concorrenti
        # senza bloccare l'event loop (pattern identico a tutor-local/backend/app/providers/stt.py).
        async with _inference_lock:
            wav_buffer = await asyncio.to_thread(
                tts_service.synthesize,
                request.input,
                voice_ref_path=request.voice,
                lang=language,
                format="wav",
            )
        samples, sample_rate = sf.read(io.BytesIO(wav_buffer.getvalue()), dtype="float32")

        # Catena atempo (pitch preservato) prima dell'eventuale mp3
        samples = audio.apply_atempo(samples, sample_rate, speed)

        if request.response_format == "mp3":
            audio_buffer = audio.encode_mp3(samples, sample_rate)
            media_type = "audio/mpeg"
            filename = "speech.mp3"
        else:
            audio_buffer = audio.encode_wav(samples, sample_rate)
            media_type = "audio/wav"
            filename = "speech.wav"

        process_time_ms = (perf_counter() - started_at) * 1000

        # Return audio stream (lista di chunk: audio_buffer è bytes)
        return StreamingResponse(
            [audio_buffer],
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
        "engine": settings.tts_engine,
        "device": tts_service.device,
        "model_loaded": tts_service.model is not None,
        "defaults": {"it": settings.voice_it, "en": settings.voice_en},
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    uvicorn.run(app, host=settings.host, port=settings.port)
