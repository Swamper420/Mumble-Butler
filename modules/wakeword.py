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

