import os

import config

try:
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False


def _models_dir():
    """Resolve openwakeword's bundled resources/models dir (None if unresolvable)."""
    try:
        import openwakeword
        import pathlib
        candidates = []
        try:
            candidates.append(
                os.path.join(
                    os.path.dirname(getattr(openwakeword, "__file__", "")),
                    "resources", "models",
                )
            )
        except Exception:
            pass
        try:
            candidates.append(
                os.path.join(
                    str(pathlib.Path(openwakeword.__file__).parent),
                    "resources", "models",
                )
            )
        except Exception:
            pass
        for c in candidates:
            if c and os.path.isdir(c):
                return c
        return candidates[0] if candidates and candidates[0] else None
    except Exception:
        return None


def _wakeword_file_present(models_dir, name, framework):
    """True only if the bundled file for builtin `name` exists in the framework's extension.

    Must be framework-strict: an .onnx Model() cannot use a .tflite file and
    vice versa. Previously an either-extension check caused a no-op ensure
    followed by NO_SUCHFILE (e.g. alexa_v0.1.tflite present but
    alexa_v0.1.onnx requested).
    """
    if not models_dir or not os.path.isdir(models_dir):
        return False
    norm = name.replace(" ", "_").lower()
    wanted = ".onnx" if (framework or "onnx") == "onnx" else ".tflite"
    try:
        files = os.listdir(models_dir)
    except OSError:
        files = []
    return any(norm in f.lower() and f.lower().endswith(wanted) for f in files)


def _ensure_base_models(requested_models=None, framework="onnx"):
    """Download base + requested wakeword models if missing.

    Version-tolerant: openwakeword==0.4.0 has no
    ``openwakeword.utils.download_models`` (added in 0.5.0+). On modern
    Python (3.12+) pip silently backtracks to 0.4.0 because 0.6.0's
    ``tflite-runtime`` dependency has no wheels there — which is exactly
    what produced ``module 'openwakeword.utils' has no attribute
    'download_models'``. So never call it unconditionally; only call it
    when it exists AND files are actually missing.
    """
    try:
        default_dir = _models_dir()
        if not default_dir:
            default_dir = ""
        # Base feature models are required regardless of wakeword choice.
        # Framework-strict: an ONNX Model() needs melspectrogram.onnx, a
        # .tflite file does NOT satisfy it (and vice versa).
        wanted_ext = ".onnx" if (framework or "onnx") == "onnx" else ".tflite"
        needed = ("melspectrogram", "embedding_model")
        missing = [
            name for name in needed
            if not os.path.exists(os.path.join(default_dir, name + wanted_ext))
        ]
        # Requested wakeword models (builtins like "alexa", "hey_jarvis").
        # Custom file paths that already exist on disk need no download.
        missing_wake = []
        for name in (requested_models or []):
            if not name:
                continue
            if os.path.exists(name):
                continue
            if not _wakeword_file_present(default_dir, name, framework):
                missing_wake.append(name)

        if not missing and not missing_wake:
            return

        import openwakeword.utils as oww_utils
        download_fn = getattr(oww_utils, "download_models", None)
        if not callable(download_fn):
            what = ", ".join(missing + missing_wake) or "models"
            print(
                "⚠️ openWakeWord models missing "
                f"({what}) but this openwakeword version "
                "has no utils.download_models (likely v0.4.0 installed due to "
                "Python 3.12+ backtrack; tflite-runtime has no wheels there). "
                "Upgrade: pip install -U 'openwakeword>=0.6.0' on Python <=3.11, "
                "or install from git main, or place the .onnx files manually. "
                "Continuing anyway — Model() may fail with a clear error."
            )
            return

        if missing_wake:
            print(f"📥 Downloading openWakeWord models if missing (needed: {', '.join(missing + missing_wake)})...")
        else:
            print("📥 Downloading openWakeWord base models if missing...")
        try:
            if default_dir:
                os.makedirs(default_dir, exist_ok=True)
        except Exception:
            pass
        try:
            # Selective download also fetches missing base/VAD models
            # (upstream always ensures FEATURE_MODELS + VAD_MODELS first).
            download_fn(missing_wake)
        except TypeError:
            # Very old download_models() takes no args.
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
                # Ensure base + requested wakeword models are present.
                # Version-tolerant: no-op when nothing is missing, graceful warning on old versions.
                _ensure_base_models(
                    requested_models=list(config.WAKEWORD_BUILTIN_MODELS or [])
                    + [p for p in (config.WAKEWORD_MODEL_PATHS or []) if not os.path.exists(p)],
                    framework=getattr(config, "WAKEWORD_INFERENCE_FRAMEWORK", "onnx") or "onnx",
                )

                print(f"🎙️ Loading openWakeWord (builtins: {config.WAKEWORD_BUILTIN_MODELS}, custom: {config.WAKEWORD_MODEL_PATHS})...")
                self.model = self.create_model_instance()
                print("✅ openWakeWord Loaded Successfully")
            except Exception as e:
                msg = str(e)
                if "NO_SUCHFILE" in msg or "File doesn't exist" in msg:
                    print(
                        f"❌ openWakeWord Load Error: {e}\n"
                        f"   → A bundled .onnx is missing and auto-download didn't provide it.\n"
                        f"   Fix (once, in your venv): python -c \"import openwakeword.utils; "
                        f"openwakeword.utils.download_models({list(config.WAKEWORD_BUILTIN_MODELS or [])})\"\n"
                        f"   Or set WAKEWORD_BUILTIN_MODELS to a model you already have "
                        f"(e.g. hey_jarvis), or WAKEWORD_LIBRARY=disabled to bypass."
                    )
                else:
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

