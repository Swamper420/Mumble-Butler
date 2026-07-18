import os
import torch
import numpy as np
import re
import urllib.request
import config
from utils import resample_audio, float_to_pcm

class Voice:
    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.engine = getattr(config, "TTS_ENGINE", "chatterbox-turbo")

        if self.engine == "chatterbox-turbo":
            print(f"🗣️ Loading Chatterbox-Turbo TTS ({self.device})...")
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            self.model = ChatterboxTurboTTS.from_pretrained(device=self.device)
            self.current_voice_id = getattr(config, "CHATTERBOX_DEFAULT_VOICE", "michael")
            self._ensure_default_voice()
        else:
            print(f"🗣️ Loading Kokoro TTS ({self.device})...")
            from kokoro import KPipeline
            self.pipeline = KPipeline(lang_code='a', device=self.device)
            self.current_voice_id = config.KOKORO_VOICE_ID

    def _ensure_default_voice(self):
        """Creates the voice directory and downloads a default speech WAV if missing."""
        voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
        os.makedirs(voice_dir, exist_ok=True)
        default_path = os.path.join(voice_dir, f"{self.current_voice_id}.wav")
        if not os.path.exists(default_path):
            print(f"📥 Downloading default voice reference to {default_path}...")
            url = "https://github.com/voxserv/audio_quality_testing_samples/raw/refs/heads/master/testaudio/16000/test01_20s.wav"
            try:
                urllib.request.urlretrieve(url, default_path)
                print("✅ Default voice reference downloaded successfully.")
            except Exception as e:
                print(f"⚠️ Failed to download default voice: {e}")

    def generate_pcm(self, text: str, voice_id: str = None):
        """Generates 48khz PCM bytes from text."""
        try:
            target_voice = voice_id or self.current_voice_id

            if self.engine == "chatterbox-turbo":
                voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
                voice_path = os.path.join(voice_dir, f"{target_voice}.wav")
                if not os.path.exists(voice_path):
                    # Fallback to default voice
                    default_voice = getattr(config, "CHATTERBOX_DEFAULT_VOICE", "michael")
                    voice_path = os.path.join(voice_dir, f"{default_voice}.wav")
                    if not os.path.exists(voice_path):
                        self._ensure_default_voice()

                if not os.path.exists(voice_path):
                    raise FileNotFoundError(f"Reference voice wav not found at {voice_path}")

                # Generate audio using Chatterbox-Turbo
                wav_tensor = self.model.generate(
                    text,
                    audio_prompt_path=voice_path,
                    temperature=getattr(config, "CHATTERBOX_TEMPERATURE", 0.8),
                )

                # Convert torch tensor to numpy float array
                audio_np = wav_tensor.detach().cpu().numpy()
                if audio_np.ndim > 1:
                    audio_np = audio_np.squeeze()

                # Resample to 48000 for Mumble
                sr = getattr(self.model, "sr", 24000)
                audio_48k = resample_audio(audio_np, sr, 48000)
                return float_to_pcm(audio_48k)
            else:
                # Kokoro path
                # Strip paralinguistic tags for Kokoro
                cleaned_text = re.sub(r'\[.*?\]', '', text)
                generator = self.pipeline(
                    cleaned_text,
                    voice=target_voice,
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
