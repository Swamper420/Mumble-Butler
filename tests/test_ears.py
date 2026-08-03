import unittest
from unittest.mock import MagicMock, patch
import requests

from modules import ears

class EarTranscribeTests(unittest.TestCase):
    @patch("modules.ears.requests.post")
    def test_transcribe_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "filename": "puhe.wav",
            "text": "Tämä on esimerkki puheentunnistuksesta suomeksi.",
            "language": "fi",
            "duration": 3.45
        }
        mock_post.return_value = mock_response

        ear = ears.Ear(api_url="http://localhost:8001")
        pcm_sample = b"\x00\x00" * 480  # 10ms of 48kHz mono 16-bit audio
        text = ear.transcribe(pcm_sample)

        self.assertEqual(text, "Tämä on esimerkki puheentunnistuksesta suomeksi.")
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args
        self.assertEqual(call_args[0], "http://localhost:8001/api/v1/transcribe")
        self.assertIn("file", call_kwargs.get("files", {}))
        data = call_kwargs.get("data", {})
        self.assertEqual(data.get("beam_size"), "5")
        self.assertEqual(data.get("vad_filter"), "true")
        self.assertEqual(data.get("word_timestamps"), "false")

    def test_transcribe_empty_pcm(self):
        ear = ears.Ear()
        self.assertEqual(ear.transcribe(b""), "")

    @patch("modules.ears.requests.post")
    def test_transcribe_api_error_returns_empty_string(self, mock_post):
        mock_post.side_effect = requests.RequestException("API connection refused")
        ear = ears.Ear()
        text = ear.transcribe(b"\x00\x00" * 100)
        self.assertEqual(text, "")

    @patch("modules.ears.requests.get")
    def test_health_check_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "healthy",
            "model": "RASMUS/whisper-large-v3-turbo-finnish-ct2",
            "language": "fi",
            "device": "cuda",
            "compute_type": "float16"
        }
        mock_get.return_value = mock_resp

        ear = ears.Ear(api_url="http://localhost:8001")
        res = ear.health_check()
        self.assertEqual(res["status"], "healthy")
        self.assertEqual(res["model"], "RASMUS/whisper-large-v3-turbo-finnish-ct2")
        mock_get.assert_called_once_with("http://localhost:8001/health", timeout=5)

    @patch("modules.ears.requests.get")
    def test_health_check_failure(self, mock_get):
        mock_get.side_effect = requests.RequestException("Connection error")
        ear = ears.Ear(api_url="http://localhost:8001")
        res = ear.health_check()
        self.assertEqual(res["status"], "error")

if __name__ == "__main__":
    unittest.main()

