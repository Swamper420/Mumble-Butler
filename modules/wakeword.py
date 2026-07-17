import numpy as np
import config
from utils import pcm_to_float, resample_audio

try:
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False

class WakewordDetector:
    def __init__(self):
        self.model = None
        self.enabled = config.WAKEWORD_LIBRARY == "openwakeword" and OPENWAKEWORD_AVAILABLE
        
        if self.enabled:
            try:
                print(f"🎙️ Loading openWakeWord (builtins: {config.WAKEWORD_BUILTIN_MODELS}, custom: {config.WAKEWORD_MODEL_PATHS})...")
                # Initialize openwakeword model
                models_to_load = []
                if config.WAKEWORD_MODEL_PATHS:
                    models_to_load.extend(config.WAKEWORD_MODEL_PATHS)
                if config.WAKEWORD_BUILTIN_MODELS:
                    models_to_load.extend(config.WAKEWORD_BUILTIN_MODELS)
                
                if models_to_load:
                    try:
                        self.model = Model(wakeword_models=models_to_load)
                    except TypeError:
                        # Fallback for older openwakeword versions
                        self.model = Model(wakeword_model_paths=models_to_load)
                else:
                    self.model = Model()
                print("✅ openWakeWord Loaded Successfully")
            except Exception as e:
                print(f"❌ openWakeWord Load Error: {e}")
                self.enabled = False
        elif config.WAKEWORD_LIBRARY == "openwakeword" and not OPENWAKEWORD_AVAILABLE:
            print("⚠️ openwakeword is configured but library is not installed/available. Wakeword detection will be bypassed (all audio processed).")

    def has_wakeword(self, raw_pcm: bytes) -> bool:
        if not self.enabled or not self.model:
            # If not enabled or available, default to True (bypass filtering)
            return True

        try:
            # 1. Convert bytes to float32
            audio_float = pcm_to_float(raw_pcm)

            # 2. Resample 48k (Mumble) -> 16k
            audio_16k_float = resample_audio(audio_float, 48000, 16000)

            # 3. Convert float32 back to int16 (required by openwakeword)
            audio_16k_int16 = (audio_16k_float * 32767.0).clip(-32768, 32767).astype(np.int16)

            # Reset model state/accumulator between predictions
            self.model.reset()

            # 4. Predict in chunks of 1280 samples (80ms)
            chunk_size = 1280
            detected = False
            for i in range(0, len(audio_16k_int16), chunk_size):
                chunk = audio_16k_int16[i:i + chunk_size]
                if len(chunk) < chunk_size:
                    # Pad last chunk with zeros
                    chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
                
                prediction = self.model.predict(chunk)
                
                # Check if any model score exceeds the threshold
                for model_name, score in prediction.items():
                    if score >= config.WAKEWORD_THRESHOLD:
                        detected = True
                        break
                if detected:
                    break

            return detected
        except Exception as e:
            print(f"❌ Error in wakeword detection: {e}")
            return True # Fallback to True to avoid dropping command on error
