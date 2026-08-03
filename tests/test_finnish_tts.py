import io
import wave
import unittest
from unittest.mock import MagicMock, patch

import config
from modules.voice import Voice

class TestFinnishTTS(unittest.TestCase):
    def test_config_tts_defaults(self):
        self.assertEqual(config.TTS_API_URL, "http://localhost:8000")
        self.assertEqual(config.TTS_VOICE, "voice_fi")
        self.assertEqual(config.TTS_LANGUAGE, "fi")
        self.assertEqual(config.TTS_SPEED, 1.0)
        self.assertEqual(config.TTS_NUM_STEP, 32)
        self.assertEqual(config.TTS_GUIDANCE_SCALE, 2.0)
        self.assertEqual(config.TTS_RESPONSE_FORMAT, "wav")
        self.assertEqual(config.TTS_SEED, 42)
        self.assertEqual(config.TTS_TIMEOUT, 30)

    @patch("requests.post")
    def test_voice_api_generation(self, mock_post):
        # Create a valid 48kHz mono 16-bit WAV in memory
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(b'\x00\x00' * 480)  # 10ms silence

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = wav_buf.getvalue()
        mock_post.return_value = mock_resp

        voice = Voice(api_url="http://localhost:8000")
        self.assertEqual(voice.engine, "external-tts-api")

        pcm = voice.generate_pcm("Tervehdys! Tämä on ääni-synteesi testi.", voice_id="voice_fi")
        self.assertIsNotNone(pcm)
        self.assertEqual(len(pcm), 480 * 2)

        mock_post.assert_called_once_with(
            "http://localhost:8000/api/v1/tts",
            json={
                "text": "Tervehdys! Tämä on ääni-synteesi testi.",
                "voice": "voice_fi",
                "language": "fi",
                "speed": 1.0,
                "num_step": 32,
                "guidance_scale": 2.0,
                "response_format": "wav",
                "seed": 42
            },
            timeout=30
        )

    @patch("requests.get")
    def test_get_available_voices(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "count": 1,
            "voices": [
                {
                    "voice_id": "voice_fi",
                    "audio_path": "storage/voices/voice_fi.wav",
                    "has_transcript": True
                }
            ]
        }
        mock_get.return_value = mock_resp

        voice = Voice(api_url="http://localhost:8000")
        voices = voice.get_available_voices()
        self.assertEqual(voices, ["voice_fi"])
        mock_get.assert_called_once_with("http://localhost:8000/api/v1/voices", timeout=30)

    @patch("requests.get")
    def test_health_check(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "ok",
            "model_loaded": True,
            "device": "cuda"
        }
        mock_get.return_value = mock_resp

        voice = Voice(api_url="http://localhost:8000")
        health = voice.health_check()
        self.assertEqual(health["status"], "ok")
        mock_get.assert_called_once_with("http://localhost:8000/health", timeout=30)

if __name__ == "__main__":
    unittest.main()
