import io
import wave
import logging
import requests
import config

logger = logging.getLogger("Ear")
STT_AVAILABLE = True

class Ear:
    def __init__(self, api_url: str = None):
        self.api_url = (api_url or getattr(config, "STT_API_URL", "http://localhost:8001")).rstrip("/")
        logger.info(f"👂 Initialized Ear module connected to external STT API at {self.api_url}")

    def transcribe(self, raw_pcm: bytes) -> str:
        """
        Transcribes 48kHz mono 16-bit PCM audio bytes by calling the external STT REST API
        POST /api/v1/transcribe via multipart/form-data.
        """
        if not raw_pcm:
            return ""

        # Package raw PCM (48kHz mono 16-bit) into WAV format in memory
        try:
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(raw_pcm)
            wav_bytes = wav_io.getvalue()
        except Exception as e:
            logger.error(f"❌ Ear: Failed to convert PCM bytes to WAV: {e}")
            return ""

        endpoint = f"{self.api_url}/api/v1/transcribe"
        timeout = getattr(config, "STT_TIMEOUT", 15)

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav")
        }

        vad_filter = getattr(config, "STT_VAD_FILTER", True)
        word_timestamps = getattr(config, "STT_WORD_TIMESTAMPS", False)
        initial_prompt = getattr(config, "STT_INITIAL_PROMPT", "")

        data = {
            "beam_size": str(int(getattr(config, "STT_BEAM_SIZE", 5))),
            "vad_filter": "true" if vad_filter else "false",
            "word_timestamps": "true" if word_timestamps else "false",
        }

        if initial_prompt:
            data["initial_prompt"] = str(initial_prompt)

        try:
            resp = requests.post(endpoint, files=files, data=data, timeout=timeout)
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, dict):
                text = result.get("text", "")
                return text.strip() if text else ""
            return ""
        except Exception as e:
            logger.error(f"❌ STT API Error transcribing audio ({endpoint}): {e}")
            return ""

    def health_check(self) -> dict:
        """Queries STT API health status from GET /health."""
        endpoint = f"{self.api_url}/health"
        timeout = getattr(config, "STT_TIMEOUT", 5)
        try:
            resp = requests.get(endpoint, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"STT API health check failed: {e}")

        return {"status": "error", "error": f"Failed to reach health endpoint on {self.api_url}"}




