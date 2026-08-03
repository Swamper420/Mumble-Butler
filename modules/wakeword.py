import numpy as np
import config

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
                # Ensure all required base models (melspectrogram, embedding, etc.) are downloaded
                import openwakeword.utils
                print("📥 Downloading openWakeWord base models if missing...")
                openwakeword.utils.download_models()

                print(f"🎙️ Loading openWakeWord (builtins: {config.WAKEWORD_BUILTIN_MODELS}, custom: {config.WAKEWORD_MODEL_PATHS})...")
                self.model = self.create_model_instance()
                print("✅ openWakeWord Loaded Successfully")
            except Exception as e:
                print(f"❌ openWakeWord Load Error: {e}")
                self.enabled = False
        elif config.WAKEWORD_LIBRARY == "openwakeword" and not OPENWAKEWORD_AVAILABLE:
            print("⚠️ openwakeword is configured but library is not installed/available. Wakeword detection will be bypassed (all audio processed).")

    def create_model_instance(self):
        if not self.enabled:
            return None
        from openwakeword.model import Model
        models_to_load = []
        if config.WAKEWORD_MODEL_PATHS:
            models_to_load.extend(config.WAKEWORD_MODEL_PATHS)
        if config.WAKEWORD_BUILTIN_MODELS:
            models_to_load.extend(config.WAKEWORD_BUILTIN_MODELS)
        
        if models_to_load:
            try:
                return Model(wakeword_models=models_to_load)
            except TypeError:
                return Model(wakeword_model_paths=models_to_load)
        else:
            return Model()

    def create_stream_model(self):
        """Creates an isolated openWakeWord Model instance for a stream."""
        if not self.enabled:
            return None
        try:
            return self.create_model_instance()
        except Exception as e:
            print(f"⚠️ Error creating stream openWakeWord model instance: {e}")
            return self.model


    def has_wakeword(self, raw_pcm: bytes) -> bool:
        if not self.enabled or not self.model:
            # If not enabled or available, default to True (bypass filtering)
            return True

        try:
            # 1. Convert bytes directly to int16 numpy array
            audio_int16 = np.frombuffer(raw_pcm, dtype=np.int16)

            # 2. Resample 48k (Mumble) -> 16k directly in int16
            from utils import resample_int16
            audio_16k_int16 = resample_int16(audio_int16, 48000, 16000)

            # Reset model state/accumulator between predictions
            self.model.reset()

            # Prepend silence chunks to bypass the model's internal warmup period (first few frames are zeroed out)
            chunk_size = 1280
            warmup_samples = 10 * chunk_size
            silence = np.zeros(warmup_samples, dtype=np.int16)
            audio_for_model = np.concatenate((silence, audio_16k_int16))

            # 4. Predict in chunks of 1280 samples (80ms)
            detected = False
            for i in range(0, len(audio_for_model), chunk_size):
                chunk = audio_for_model[i:i + chunk_size]
                if len(chunk) < chunk_size:
                    # Pad last chunk with zeros
                    chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
                
                prediction = self.model.predict(chunk)
                
                for score in prediction.values():
                    if score >= config.WAKEWORD_THRESHOLD:
                        detected = True
                        break
                if detected:
                    break

            return detected
        except Exception as e:
            print(f"❌ Error in wakeword detection: {e}")
            return True # Fallback to True to avoid dropping command on error
