import io
import re
import wave
import logging
import subprocess
import requests
import numpy as np

import config
from utils import resample_int16

logger = logging.getLogger("Voice")

class Voice:
    def __init__(self, api_url: str = None):
        self.api_url = (api_url or getattr(config, "TTS_API_URL", "http://localhost:8000")).rstrip("/")
        self.engine = "external-tts-api"
        self._current_voice_id = getattr(config, "TTS_VOICE", "mieto_fi")
        logger.info(f"🗣️ Initialized Voice module connected to external TTS API at {self.api_url}")

    @property
    def current_voice_id(self) -> str:
        return self._current_voice_id

    @current_voice_id.setter
    def current_voice_id(self, voice_id: str):
        if voice_id:
            self._current_voice_id = voice_id

    def reload_engine(self):
        """Reloads/checks connection to external TTS API."""
        logger.info(f"🔄 Re-checking external TTS API connection at {self.api_url}...")
        self.health_check()
        return self

    def sanitize_tts_text(self, text: str) -> str:
        """Sanitizes and normalizes input text for TTS generation."""
        if not text:
            return ""
        cleaned = str(text).strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
        return cleaned.strip()

    def generate_pcm(self, text: str, voice_id: str = None) -> bytes:
        """Generates 48kHz mono 16-bit PCM bytes from text using OpenAI-compatible /v1/audio/speech API."""
        cleaned_text = self.sanitize_tts_text(text)
        if not cleaned_text:
            return None

        target_voice = voice_id or self.current_voice_id
        endpoint = f"{self.api_url}/v1/audio/speech"
        timeout = getattr(config, "TTS_TIMEOUT", 30)

        payload = {
            "model": getattr(config, "TTS_MODEL", "omnivoice"),
            "input": cleaned_text,
            "voice": target_voice,
            "response_format": getattr(config, "TTS_RESPONSE_FORMAT", "wav"),
            "speed": float(getattr(config, "TTS_SPEED", 1.0)),
        }

        try:
            resp = requests.post(endpoint, json=payload, timeout=timeout)
            resp.raise_for_status()
            audio_bytes = resp.content
            if not audio_bytes:
                return None

            return self._convert_audio_to_pcm48k(audio_bytes)
        except Exception as e:
            logger.error(f"TTS API Error generating audio ({endpoint}): {e}")
            return None

    def _convert_audio_to_pcm48k(self, audio_bytes: bytes) -> bytes:
        """Converts binary audio bytes (WAV or format supported via ffmpeg) to 48kHz mono 16-bit PCM bytes."""
        # 1. Fast path for WAV audio
        try:
            with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
                sr = wf.getframerate()
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                raw_frames = wf.readframes(wf.getnframes())

                if sampwidth == 2:
                    audio_data = np.frombuffer(raw_frames, dtype=np.int16)
                elif sampwidth == 4:
                    audio_data = (np.frombuffer(raw_frames, dtype=np.int32) >> 16).astype(np.int16)
                elif sampwidth == 1:
                    audio_data = ((np.frombuffer(raw_frames, dtype=np.uint8).astype(np.int16) - 128) << 8)
                else:
                    raise ValueError(f"Unsupported sample width: {sampwidth}")

                if nchannels > 1:
                    audio_data = audio_data.reshape(-1, nchannels).mean(axis=1).astype(np.int16)

                if sr != 48000:
                    audio_data = resample_int16(audio_data, sr, 48000)

                return audio_data.tobytes()
        except Exception:
            pass

        # 2. Robust fallback via FFmpeg (handles MP3, OGG, FLAC, AAC, etc.)
        try:
            proc = subprocess.Popen(
                ['ffmpeg', '-y', '-i', 'pipe:0', '-f', 's16le', '-ar', '48000', '-ac', '1', 'pipe:1'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            out, _ = proc.communicate(input=audio_bytes, timeout=10)
            if proc.returncode == 0 and out:
                return out
        except Exception as e:
            logger.error(f"FFmpeg conversion fallback failed: {e}")

        return None

    def get_available_voices_details(self) -> list:
        """Fetches detailed list of available voices from external API GET /api/v1/voices."""
        endpoint = f"{self.api_url}/api/v1/voices"
        timeout = getattr(config, "TTS_TIMEOUT", 10)
        try:
            resp = requests.get(endpoint, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "voices" in data:
                return data.get("voices", [])
            elif isinstance(data, list):
                return data
        except Exception as e:
            logger.warning(f"Failed to fetch voice details from TTS API ({endpoint}): {e}")

        return []

    def get_available_voices(self) -> list:
        """Fetches list of available voice IDs from external API GET /api/v1/voices."""
        voices_details = self.get_available_voices_details()
        voice_ids = []
        for v in voices_details:
            if isinstance(v, dict) and "voice_id" in v:
                voice_ids.append(v["voice_id"])
            elif isinstance(v, str):
                voice_ids.append(v)
        if voice_ids:
            return sorted(list(set(voice_ids)))

        return [self.current_voice_id]


    def reload_voices(self) -> bool:
        """Triggers voice catalog reload on external API POST /api/v1/voices/reload."""
        endpoint = f"{self.api_url}/api/v1/voices/reload"
        timeout = getattr(config, "TTS_TIMEOUT", 10)
        try:
            resp = requests.post(endpoint, timeout=timeout)
            if resp.status_code in (200, 201, 204):
                return True
        except Exception as e:
            logger.warning(f"Failed to reload voices on TTS API: {e}")

        return False

    def health_check(self) -> dict:
        """Queries health status from external API GET /health."""
        endpoint = f"{self.api_url}/health"
        timeout = getattr(config, "TTS_TIMEOUT", 5)
        try:
            resp = requests.get(endpoint, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"TTS API health check failed: {e}")

        return {"status": "error", "error": f"Failed to reach health endpoint on {self.api_url}"}
