import os
import time
import json
import unittest
import urllib.request
import urllib.parse
from unittest.mock import MagicMock, patch

import config
from modules.voice import Voice
from modules.web_server import BotWebServer, WebRequestHandler

class TestTTSAPIServer(unittest.TestCase):
    def test_voice_api_model_init(self):
        """Test initializing Voice with specified API model."""
        with patch.object(Voice, "_load_model_instance", return_value=MagicMock()) as mock_load:
            voice = Voice(model_type="custom_api_model")
            self.assertEqual(voice.default_model_type, "custom_api_model")
            mock_load.assert_called_with("custom_api_model")

    def test_voice_reload_engine(self):
        """Test Voice.reload_engine functionality."""
        with patch.object(Voice, "_load_model_instance", return_value=MagicMock()) as mock_load:
            voice = Voice(model_type="test_model")
            mock_load.reset_mock()
            
            voice.reload_engine()
            mock_load.assert_called_with("test_model")

    def test_standalone_tts_api_server_endpoints_and_autorecovery(self):
        """Test standalone web server TTS API endpoint and auto-recovery retry mechanism."""
        mock_voice = MagicMock()
        # First call fails (CUDA Error simulation), second call succeeds
        mock_voice.generate_pcm.side_effect = [
            Exception("CUDA error: an illegal memory access occurred"),
            b"\x00\x00" * 4800
        ]
        mock_voice.reload_engine = MagicMock()

        WebRequestHandler.bot_instance = None
        WebRequestHandler.fallback_voice = mock_voice

        server = BotWebServer(bot_instance=None, host="127.0.0.1", port=8098)
        server.start()
        time.sleep(0.2)

        try:
            base_url = "http://127.0.0.1:8098"
            req = urllib.request.Request(f"{base_url}/api/tts?text=Test+auto+recovery+retry&format=json")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["status"], "ok")
                self.assertEqual(data["text"], "Test auto recovery retry")

            # Verify reload_engine was triggered on failure
            mock_voice.reload_engine.assert_called_once()
            self.assertEqual(mock_voice.generate_pcm.call_count, 2)
        finally:
            server.stop()
            WebRequestHandler.fallback_voice = None

    def test_bot_tts_api_subprocess_lifecycle(self):
        """Test bot spawning and shutting down isolated TTS API subprocess."""
        from bot import MadnessBot

        with patch("subprocess.Popen") as mock_popen, patch.object(MadnessBot, "__init__", return_value=None):
            bot = MadnessBot()
            bot.logger = MagicMock()
            bot.tts_api_process = None

            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            bot._start_tts_api_process()
            mock_popen.assert_called_once()
            self.assertEqual(bot.tts_api_process, mock_proc)

            bot._stop_tts_api_process()
            mock_proc.terminate.assert_called_once()
            self.assertIsNone(bot.tts_api_process)

if __name__ == "__main__":
    unittest.main()
