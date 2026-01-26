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

    def load_model(self):
        if self.model is None:
            # Auto-download if missing
            if not os.path.exists(self.model_path):
                logger.info(f"Model path {self.model_path} not found. Attempting auto-download...")
                try:
                    # heuristic to guess repo_id if it's standard structure, otherwise use Qwen/Qwen3-TTS-12Hz-0.6B-Base as default
                    # Assuming the parent dir of model_path is the base for models
                    # If model_path is "./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base"
                    # We can try to infer the repo_id or just fail if it's a custom path.
                    # Let's map filename to repo? Or just use a default fallback.
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
            if self.flash_attn:
                kwargs["attn_implementation"] = "flash_attention_2"

            self.model = Qwen3TTSModel.from_pretrained(
                self.model_path, 
                torch_dtype=torch_dtype,
                **kwargs
            )
            
            # Move to device if supported
            if hasattr(self.model, "to"):
                self.model.to(self.device)
            elif hasattr(self.model, "model") and hasattr(self.model.model, "to"):
                 self.model.model.to(self.device)

            logger.info("Model loaded successfully.")

    def synthesize(self, text: str, voice_ref_path: str = None, lang: str = "it"):
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
        # 1. Check if absolute or existing path passed
        # 2. Check in voices_dir
        # 3. Fallback to default
        
        target_voice = voice_ref_path
        if not target_voice or not os.path.exists(target_voice):
            # check in voices dir
            candidate = os.path.join(self.voices_dir, os.path.basename(voice_ref_path) if voice_ref_path else "default_ref.wav")
            if os.path.exists(candidate):
                target_voice = candidate
            else:
                 # fallback
                 target_voice = os.path.join(self.voices_dir, "default_ref.wav")
        
        if not os.path.exists(target_voice):
             # Ensure default exists if we fell back to it
             if "default_ref.wav" in target_voice:
                  # Create dummy
                  try:
                      import numpy as np
                      sr=16000
                      noise = np.random.uniform(-0.1, 0.1, sr*3)
                      sf.write(target_voice, noise, sr)
                  except:
                      logger.warning("Could not create default_ref.wav")

        if not os.path.exists(target_voice):
             logger.error(f"Voice file {target_voice} not found.")
             raise FileNotFoundError(f"Voice file {target_voice} not found.")

        try:
            # Persistent Cache Logic
            # Key based on filename + modification time to invalidate on change
            voice_name = os.path.basename(target_voice)
            mtime = os.path.getmtime(target_voice)
            cache_name = f"{voice_name}_{mtime}.pt"
            cache_path = os.path.join(self.cache_dir, cache_name)

            prompt = None
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
            
            # Ensure prompt is on the correct device/dtype if necessary
            # (Note: prompt might be a dictionary or custom object, so .to() might not work directly on it 
            # if it's not a tensor or nn.Module. If it is a dict of tensors, we could move them.)
            # Qwen3TTS prompt is usually a dict or custom class. 
            # If Qwen3TTSModel handles device movement during inference, we might be fine, 
            # but let's assume 'map_location' in load handled it for the cached version.

            # The Base model requires generate_voice_clone
            wavs, sr = self.model.generate_voice_clone(
                text=text,
                language=full_lang,
                voice_clone_prompt=prompt
            )
            
            # wavs is a list of numpy arrays, we take the first one
            audio = wavs[0]
            
            buf = io.BytesIO()
            sf.write(buf, audio, samplerate=sr, format='WAV')
            buf.seek(0)
            return buf
            
        except AttributeError:
             # Fallback if we accidentally loaded a different model type that DOES support synthesize?
             # But we know we are using Base.
             logger.error("Model does not support generate_voice_clone or synthesize.")
             raise

