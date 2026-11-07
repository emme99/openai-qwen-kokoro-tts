import torch
import soundfile as sf
import io
import os
import logging
import pickle
from huggingface_hub import snapshot_download

# We wrap the import in try-except to avoid crashing if dependencies aren't fully installed during development interrogation
try:
    from qwen_tts.infer import Qwen3TTSModel
except ImportError:
    pass

from qwen_tts import Qwen3TTSModel # Re-importing cleanly

logger = logging.getLogger(__name__)

class QwenTTSService:
    def __init__(self, model_path, device="cpu", dtype="float32", flash_attn=False):
        self.model_path = model_path
        self.device = device
        self.dtype = dtype
        self.flash_attn = flash_attn
        self.model = None
        self.voices_dir = "voices"
        self.cache_dir = os.path.join(self.voices_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        # In-memory cache for the last used voice prompt
        self.last_voice_path = None
        self.last_prompt = None

    def load_model(self):
        if self.model is not None:
            # Model already loaded
            return

        # Auto-download if missing
        if not os.path.exists(self.model_path):
            logger.info(f"Model path {self.model_path} not found. Attempting auto-download...")
            try:
                # heuristic to guess repo_id if it's standard structure, otherwise use Qwen/Qwen3-TTS-12Hz-0.6B-Base as default
                repo_id = "Qwen/Qwen3-TTS-12Hz-0.6B-Base" 
                # If the user specified a specific path in config that ends in a known model name, use that.
                if "Qwen3-TTS" in self.model_path:
                    parts = self.model_path.split("/")
                    # Try to find the part that looks like the model name
                    for part in parts:
                            if "Qwen3-TTS" in part:
                                repo_id = f"Qwen/{part}"
                                break
                
                logger.info(f"Downloading {repo_id} to {self.model_path}...")
                snapshot_download(
                    repo_id=repo_id,
                    local_dir=self.model_path,
                    local_dir_use_symlinks=False
                )
            except Exception as e:
                logger.error(f"Failed to download model: {e}")
                raise FileNotFoundError(f"Model path not found and download failed: {self.model_path}")

        logger.info(f"Loading model on {self.device} (dtype={self.dtype}, flash_attn={self.flash_attn})...")
        
        # Map string dtype to torch dtype
        torch_dtype = torch.float32
        if self.dtype == "float16":
            torch_dtype = torch.float16
        elif self.dtype == "bfloat16":
            torch_dtype = torch.bfloat16
            
        kwargs = {}
        if self.device == "mps":
            if not torch.backends.mps.is_available():
                raise RuntimeError("MPS is not available in this PyTorch installation.")
            kwargs["device_map"] = self.device
        if self.flash_attn:
            kwargs["attn_implementation"] = "flash_attention_2"

        self.model = Qwen3TTSModel.from_pretrained(
            self.model_path, 
            dtype=torch_dtype,
            **kwargs
        )
        
        # Move to device if supported
        if self.device != "mps":
            if hasattr(self.model, "to"):
                self.model.to(self.device)
            elif hasattr(self.model, "model") and hasattr(self.model.model, "to"):
                self.model.model.to(self.device)

        logger.info("Model loaded successfully.")

    def synthesize(self, text: str, voice_ref_path: str = None, lang: str = "it", format: str = "wav"):
        if self.model is None:
            self.load_model()
            
        # Map simple language codes to model-supported full names
        lang_map = {
            "it": "Italian",
            "en": "English",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "de": "German",
            "fr": "French",
            "ru": "Russian",
            "es": "Spanish",
            "pt": "Portuguese"
        }
        
        full_lang = lang_map.get(lang.lower(), lang)
            
        logger.info(f"Synthesizing text: '{text}' (lang={full_lang})")
        
        # Resolve voice path
        
        target_voice = None
        
        if voice_ref_path:
            # 1a. Exact path check
            if os.path.exists(voice_ref_path):
                target_voice = voice_ref_path
            else:
                # 1b/c. Check voices dir
                # Clean the name to avoid path traversal logic if basic name
                safe_name = os.path.basename(voice_ref_path)
                
                # Check with .wav extension if missing
                candidate_list = []
                if not safe_name.lower().endswith(".wav"):
                     candidate_list.append(os.path.join(self.voices_dir, f"{safe_name}.wav"))
                
                candidate_list.append(os.path.join(self.voices_dir, safe_name))
                
                for candidate in candidate_list:
                    if os.path.exists(candidate):
                        target_voice = candidate
                        break
        
        # Fallback Logic
        if not target_voice:
             logger.info(f"Voice '{voice_ref_path}' not found. Looking for defaults...")
             default_candidates = [
                 os.path.join(self.voices_dir, "default.wav"),
             ]
             
             for candidate in default_candidates:
                 if os.path.exists(candidate):
                     target_voice = candidate
                     logger.info(f"Using fallback voice: {target_voice}")
                     break
        
        if not target_voice:
             # If still no voice, create a dummy default.wav
             logger.warning("No default voice found. Creating default.wav from noise.")
             target_voice = os.path.join(self.voices_dir, "default.wav")
             try:
                 import numpy as np
                 sr=16000
                 noise = np.random.uniform(-0.1, 0.1, sr*3)
                 sf.write(target_voice, noise, sr)
             except Exception as e:
                 logger.error(f"Could not create default voice: {e}")

        if not os.path.exists(target_voice):
             logger.error(f"Voice file {target_voice} not found.")
             raise FileNotFoundError(f"Voice file {target_voice} not found.")

        try:
            # Check in-memory cache first
            prompt = None
            voice_name = os.path.basename(target_voice)
            mtime = os.path.getmtime(target_voice)
            
            # Key for checking if checking changed
            # We use target_voice path as ID. But mtime helps invalidation.
            # logic: if self.last_voice_path == target_voice, we assume reusing same prompt 
            # (unless we want strict mtime check every time? OS call is cheap).
            
            if self.last_voice_path == target_voice and self.last_prompt is not None:
                # check mtime validity? 
                # Doing stat every time is safer.
                if hasattr(self, 'last_voice_mtime') and self.last_voice_mtime == mtime:
                    logger.info(f"Using in-memory cached prompt for {target_voice}")
                    prompt = self.last_prompt
            
            if prompt is None:
                # Fallback to Disk Cache Logic
                # Key based on filename + modification time to invalidate on change
                cache_name = f"{voice_name}_{mtime}.pt"
                cache_path = os.path.join(self.cache_dir, cache_name)

                if os.path.exists(cache_path):
                    logger.info(f"Loading cached prompt from {cache_path}")
                    try:
                        # weights_only=False is required for custom classes/structs in older pytorch versions or complex objects
                        # We trust our local cache.
                        prompt = torch.load(cache_path, map_location=self.device, weights_only=False)
                    except Exception as e:
                        logger.warning(f"Failed to load cache: {e}")
                
                if prompt is None:
                    logger.info(f"Computing prompt for {target_voice}...")
                    # Create the prompt features once
                    prompt = self.model.create_voice_clone_prompt(
                        ref_audio=target_voice,
                        x_vector_only_mode=True
                    )
                    # Save to cache
                    try:
                        torch.save(prompt, cache_path)
                    except Exception as e:
                        logger.warning(f"Failed to save cache: {e}")
                
                # Update in-memory cache
                self.last_voice_path = target_voice
                self.last_voice_mtime = mtime
                self.last_prompt = prompt

            # The Base model requires generate_voice_clone
            wavs, sr = self.model.generate_voice_clone(
                text=text,
                language=full_lang,
                voice_clone_prompt=prompt
            )
            
            # wavs is a list of numpy arrays, we take the first one
            audio = wavs[0]
            
            # Initial WAV generation in memory
            wav_buf = io.BytesIO()
            sf.write(wav_buf, audio, samplerate=sr, format='WAV')
            wav_buf.seek(0)
            
            if format == "wav":
                return wav_buf
            elif format == "mp3":
                try:
                    import subprocess
                    process = subprocess.Popen(
                        ["ffmpeg", "-i", "pipe:0", "-f", "mp3", "pipe:1", "-v", "quiet"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate(input=wav_buf.read())
                    
                    if process.returncode != 0:
                        logger.error(f"FFmpeg error: {stderr.decode()}")
                        # Fallback to wav on failure? Or raise? 
                        # Raising is better so client knows something went wrong
                        raise RuntimeError(f"FFmpeg conversion failed: {stderr.decode()}")
                        
                    return io.BytesIO(stdout)
                except Exception as e:
                    logger.error(f"MP3 conversion failed: {e}")
                    raise
            else: 
                 # Fallback or error? OpenAI defaults to mp3, but if unknown format, maybe error?
                 # For now fallback to wav to be safe
                 logger.warning(f"Unknown format {format}, returning WAV")
                 return wav_buf
            
        except AttributeError:
             # Fallback if we accidentally loaded a different model type that DOES support synthesize?
             # But we know we are using Base.
             logger.error("Model does not support generate_voice_clone or synthesize.")
             raise


