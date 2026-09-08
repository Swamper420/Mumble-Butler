import os

import config

try:
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False


def _ensure_base_models():
    """Download base models (melspectrogram/embedding/VAD) if missing.

    Version-tolerant: openwakeword==0.4.0 has no
    ``openwakeword.utils.download_models`` (added in 0.5.0+). On modern
    Python (3.12+) pip silently backtracks to 0.4.0 because 0.6.0's
    ``tflite-runtime`` dependency has no wheels there — which is exactly
    what produced ``module 'openwakeword.utils' has no attribute
    'download_models'``. So never call it unconditionally; only call it
    when it exists AND files are actually missing.
    """
    try:
        import openwakeword
        import pathlib
        default_dir = os.path.join(
            os.path.dirname(getattr(openwakeword, "__file__", "")),
            "resources", "models",
        )
        # Base feature models are required regardless of wakeword choice.
        # Check for either .onnx or .tflite variants.
        needed = ("melspectrogram", "embedding_model")
        missing = [
            name for name in needed
            if not (
                os.path.exists(os.path.join(default_dir, name + ".onnx"))
                or os.path.exists(os.path.join(default_dir, name + ".tflite"))
            )
        ]
        # Also check pathlib fallback if __file__ was odd
        if not os.path.isdir(default_dir):
            try:
                alt = os.path.join(
                    str(pathlib.Path(openwakeword.__file__).parent),
                    "resources", "models",
                )
                if os.path.isdir(alt):
                    default_dir = alt
                    missing = [
                        name for name in needed
                        if not (
                            os.path.exists(os.path.join(default_dir, name + ".onnx"))
                            or os.path.exists(os.path.join(default_dir, name + ".tflite"))
                        )
                    ]
                else:
                    missing = list(needed)
            except Exception:
                missing = list(needed)

        if not missing:
            return

        import openwakeword.utils as oww_utils
        download_fn = getattr(oww_utils, "download_models", None)
        if not callable(download_fn):
            print(
                "⚠️ openWakeWord base models missing "
                f"({', '.join(missing)}) but this openwakeword version "
                "has no utils.download_models (likely v0.4.0 installed due to "
                "Python 3.12+ backtrack; tflite-runtime has no wheels there). "
                "Upgrade: pip install -U 'openwakeword>=0.6.0' on Python <=3.11, "
                "or install from git main, or place the .onnx files manually. "
                "Continuing anyway — Model() may fail with a clear error."
            )
            return

        print("📥 Downloading openWakeWord base models if missing...")
        try:
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            pass
        download_fn()
    except ImportError as e:
        print(f"⚠️ Could not check/download openWakeWord base models: {e}")
    except PermissionError as e:
        print(
            f"⚠️ No permission to download openWakeWord models to site-packages: {e}. "
            "Re-run once with write permission or pre-download the models."
        )
    except Exception as e:
        # Never fatal — let Model() raise the real error below.
        print(f"⚠️ Base model download check skipped: {e}")

class WakewordDetector:
    def __init__(self):
        self.model = None
        self.enabled = config.WAKEWORD_LIBRARY == "openwakeword" and OPENWAKEWORD_AVAILABLE
        
        if self.enabled:
            try:
                # Ensure all required base models (melspectrogram, embedding, etc.) are present.
                # Version-tolerant: no-op when nothing is missing, graceful warning on old versions.
                _ensure_base_models()

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

        # Prefer ONNX: onnxruntime has wheels for Python 3.12/3.13/3.14,
        # while tflite-runtime (required by openwakeword 0.6.0's default
        # "tflite" framework on Linux) does not — pip then backtracks to
        # openwakeword 0.4.0, which lacks utils.download_models.
        framework = getattr(config, "WAKEWORD_INFERENCE_FRAMEWORK", "onnx") or "onnx"

        if models_to_load:
            # New API (>=0.5.0): wakeword_models + inference_framework
            try:
                return Model(wakeword_models=models_to_load, inference_framework=framework)
            except TypeError as e:
                msg = str(e)
                # Old API (0.4.0): no inference_framework kwarg, ONNX-only
                if "inference_framework" in msg:
                    try:
                        return Model(wakeword_models=models_to_load)
                    except TypeError:
                        return Model(wakeword_model_paths=models_to_load)
                # New API but old kwarg name
                if "wakeword_models" in msg:
                    try:
                        return Model(wakeword_model_paths=models_to_load, inference_framework=framework)
                    except TypeError:
                        return Model(wakeword_model_paths=models_to_load)
                raise
        else:
            try:
                return Model(inference_framework=framework)
            except TypeError:
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

