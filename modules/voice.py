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
        self.engine = "chatterbox-nano"
        self.conds_cache = {}

        # Optimize PyTorch CPU threading & CUDA matrix flags to relieve CPU bottlenecks
        cpu_cores = os.cpu_count() or 4
        if hasattr(torch, "set_num_threads"):
            torch.set_num_threads(min(cpu_cores, 8))
        if hasattr(torch, "set_num_interop_threads"):
            torch.set_num_interop_threads(min(cpu_cores, 4))
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

        print(f"🗣️ Loading Chatterbox-Nano TTS ({self.device})...")
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        self.model = ChatterboxTurboTTS.from_pretrained(device=self.device, nano=True)
        self.current_voice_id = getattr(config, "CHATTERBOX_DEFAULT_VOICE", "michael")
        self._ensure_default_voice()

        # Pre-warm default voice
        voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
        default_path = os.path.join(voice_dir, f"{self.current_voice_id}.wav")
        if os.path.exists(default_path):
            try:
                print(f"🔥 Pre-warming conditionals cache for default voice: {self.current_voice_id}...")
                with torch.inference_mode():
                    self.model.prepare_conditionals(default_path)
                self.conds_cache[self.current_voice_id] = self.model.conds
            except Exception as e:
                print(f"⚠️ Failed to pre-warm default voice cache: {e}")

    def clear_voice_cache(self, keep_voice: str = None):
        """Clears cached voice conditionals from dictionary and frees GPU VRAM."""
        if keep_voice:
            keys_to_del = [k for k in self.conds_cache if k != keep_voice]
            for k in keys_to_del:
                del self.conds_cache[k]
        else:
            self.conds_cache.clear()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
        """Generates 48khz PCM bytes from text using Chatterbox-Nano."""
        try:
            target_voice = voice_id or self.current_voice_id
            voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
            voice_path = os.path.join(voice_dir, f"{target_voice}.wav")

            # Check if voice_path exists, fallback if not
            if not os.path.exists(voice_path):
                default_voice = getattr(config, "CHATTERBOX_DEFAULT_VOICE", "michael")
                voice_path = os.path.join(voice_dir, f"{default_voice}.wav")
                if not os.path.exists(voice_path):
                    self._ensure_default_voice()
                target_voice = default_voice

            if not os.path.exists(voice_path):
                raise FileNotFoundError(f"Reference voice wav not found at {voice_path}")

            with torch.inference_mode():
                # Load voice conditionals from cache or prepare and cache them
                if target_voice in self.conds_cache:
                    self.model.conds = self.conds_cache[target_voice]
                else:
                    # Evict previous voice conditionals if cache limit reached
                    max_cache = getattr(config, "CHATTERBOX_VOICE_CACHE_LIMIT", 1)
                    if max_cache > 0:
                        while len(self.conds_cache) >= max_cache:
                            oldest_voice = next(iter(self.conds_cache))
                            del self.conds_cache[oldest_voice]
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()

                    self.model.prepare_conditionals(voice_path)
                    self.conds_cache[target_voice] = self.model.conds

                # Generate audio using Chatterbox-Nano with cached conditionals
                wav_tensor = self.model.generate(
                    text,
                    audio_prompt_path=None,
                    temperature=getattr(config, "CHATTERBOX_TEMPERATURE", 0.8),
                )

                # Resample and convert float32 to PCM int16 directly on GPU tensor if available
                sr = getattr(self.model, "sr", 24000)
                if torch.is_tensor(wav_tensor) and wav_tensor.numel() > 0:
                    curr = wav_tensor.detach()
                    if sr != 48000:
                        if curr.ndim == 1:
                            curr = curr.unsqueeze(0).unsqueeze(0)
                        elif curr.ndim == 2:
                            curr = curr.unsqueeze(1)
                        target_len = int(curr.shape[-1] * (48000 / sr))
                        curr = torch.nn.functional.interpolate(
                            curr, size=target_len, mode='linear', align_corners=False
                        ).squeeze()
                    else:
                        curr = curr.squeeze()

                    pcm_tensor = (curr * 32767).clamp(-32768, 32767).to(torch.int16)
                    return pcm_tensor.cpu().numpy().tobytes()

                # Fallback for non-tensor outputs
                audio_np = wav_tensor.detach().cpu().numpy() if torch.is_tensor(wav_tensor) else wav_tensor
                if audio_np.ndim > 1:
                    audio_np = audio_np.squeeze()

                audio_48k = resample_audio(audio_np, sr, 48000)
                return float_to_pcm(audio_48k)
        except Exception as e:
            print(f"TTS Error: {e}")
            return None
