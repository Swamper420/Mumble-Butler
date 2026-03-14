import os
import torch
import numpy as np
import re
from kokoro import KPipeline
import config
from utils import resample_audio, float_to_pcm

class Voice:
    def __init__(self):
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"🗣️ Loading Kokoro TTS ({device})...")
        self.pipeline = KPipeline(lang_code='a', device=device)
        self.current_voice_id = config.KOKORO_VOICE_ID

    def generate_pcm(self, text: str):
        """Generates 48khz PCM bytes from text."""
        try:
            # Kokoro generates at 24khz
            generator = self.pipeline(
                text,
                voice=self.current_voice_id,
                speed=config.KOKORO_SPEED,
                split_pattern=r'\n+'
            )

            segments = [audio for _, _, audio in generator]
            if not segments: return None

            audio_24k = np.concatenate(segments)

            # Resample 24k -> 48k for Mumble
            audio_48k = resample_audio(audio_24k, 24000, 48000)

            return float_to_pcm(audio_48k)
        except Exception as e:
            print(f"TTS Error: {e}")
            return None
