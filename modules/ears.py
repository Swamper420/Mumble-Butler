import numpy as np
import config
from utils import resample_audio, pcm_to_float

try:
    from faster_whisper import WhisperModel
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False

class Ear:
    def __init__(self):
        self.model = None
        if STT_AVAILABLE:
            try:
                print(f"👂 Loading Whisper ({config.WHISPER_DEVICE})...")
                self.model = WhisperModel(
                    config.WHISPER_MODEL_SIZE,
                    device=config.WHISPER_DEVICE,
                    compute_type=config.WHISPER_COMPUTE
                )
            except Exception as e:
                print(f"❌ Whisper Load Error: {e}")

    def transcribe(self, raw_pcm: bytes) -> str:
        if not self.model: return ""

        # 1. Convert bytes to float32
        audio_float = pcm_to_float(raw_pcm)

        # 2. Resample 48k (Mumble) -> 16k (Whisper)
        audio_16k = resample_audio(audio_float, 48000, 16000)

        # 3. Transcribe
        segments, _ = self.model.transcribe(
            audio_16k,
            language=config.WHISPER_LANGUAGE,
            beam_size=5,
            task="transcribe"
        )
        return " ".join([s.text for s in segments]).strip()
import numpy as np
import config
from utils import resample_audio, pcm_to_float

try:
    from faster_whisper import WhisperModel
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False

class Ear:
    def __init__(self):
        self.model = None
        if STT_AVAILABLE:
            try:
                print(f"👂 Loading Whisper ({config.WHISPER_DEVICE})...")
                self.model = WhisperModel(
                    config.WHISPER_MODEL_SIZE,
                    device=config.WHISPER_DEVICE,
                    compute_type=config.WHISPER_COMPUTE
                )
            except Exception as e:
                print(f"❌ Whisper Load Error: {e}")

    def transcribe(self, raw_pcm: bytes) -> str:
        if not self.model: return ""

        # 1. Convert bytes to float32
        audio_float = pcm_to_float(raw_pcm)

        # 2. Resample 48k (Mumble) -> 16k (Whisper)
        audio_16k = resample_audio(audio_float, 48000, 16000)

        # 3. Transcribe
        segments, _ = self.model.transcribe(
            audio_16k,
            language=config.WHISPER_LANGUAGE,
            beam_size=5,
            task="transcribe"
        )
        return " ".join([s.text for s in segments]).strip()
