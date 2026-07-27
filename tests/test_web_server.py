import os
import time
import json
import unittest
import urllib.request
import urllib.parse
import tempfile
import config
from modules.web_server import ConfigManager, BotWebServer

class DummyBot:
    def __init__(self):
        self.listening_enabled = True
        self.start_time = time.time()
        self.mumble = None
        self.brain = type("Brain", (), {"llm": True, "memory_enabled": True})()
        self.ear = True
        self.voice = True
        self.wakeword_detector = type("Wakeword", (), {"enabled": True})()

    def get_status(self):
        return {
            "Mumble": "Disconnected",
            "Uptime": "0h 0m 10s",
            "LLM": "Online",
            "Listening": "ON" if self.listening_enabled else "OFF",
        }


class TestWebServer(unittest.TestCase):
    def test_dynamic_config_discovery(self):
        # Set a temporary variable on config module
        config.TEST_DYNAMIC_VARIABLE_XYZ = "Hello HTMX"
        
        config_items = ConfigManager.get_all_config()
        keys = [item["key"] for item in config_items]

        self.assertIn("TEST_DYNAMIC_VARIABLE_XYZ", keys)
        self.assertIn("OLLAMA_KEEP_ALIVE", keys)
        self.assertIn("LLM_CONTEXT_SIZE", keys)
        self.assertIn("OLLAMA_TIMEOUT", keys)
        
        # Find item
        target = next(i for i in config_items if i["key"] == "TEST_DYNAMIC_VARIABLE_XYZ")
        self.assertEqual(target["value"], "Hello HTMX")
        self.assertEqual(target["type"], "str")

        # Cleanup
        delattr(config, "TEST_DYNAMIC_VARIABLE_XYZ")

    def test_config_type_updates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = os.path.join(tmp_dir, ".env")
            original_cwd = os.getcwd()
            os.chdir(tmp_dir)

            try:
                config.TEST_INT_VAL = 42
                config.TEST_BOOL_VAL = False
                config.TEST_LIST_VAL = ["a", "b"]

                # Test updating int
                success, msg = ConfigManager.update_config_var("TEST_INT_VAL", "99")
                self.assertTrue(success)
                self.assertEqual(config.TEST_INT_VAL, 99)

                # Test updating bool
                success, msg = ConfigManager.update_config_var("TEST_BOOL_VAL", "True")
                self.assertTrue(success)
                self.assertTrue(config.TEST_BOOL_VAL)

                # Test updating list
                success, msg = ConfigManager.update_config_var("TEST_LIST_VAL", "apple, banana, cherry")
                self.assertTrue(success)
                self.assertEqual(config.TEST_LIST_VAL, ["apple", "banana", "cherry"])

                # Verify persistence in .env
                self.assertTrue(os.path.exists(env_file))
                with open(env_file, "r", encoding="utf-8") as f:
                    env_text = f.read()
                self.assertIn("TEST_INT_VAL=99", env_text)
                self.assertIn("TEST_BOOL_VAL=True", env_text)
                self.assertIn("TEST_LIST_VAL=apple,banana,cherry", env_text)

            finally:
                os.chdir(original_cwd)
                for attr in ["TEST_INT_VAL", "TEST_BOOL_VAL", "TEST_LIST_VAL"]:
                    if hasattr(config, attr):
                        delattr(config, attr)

    def test_web_server_endpoints(self):
        bot = DummyBot()
        server = BotWebServer(bot_instance=bot, host="127.0.0.1", port=8099)
        server.start()

        time.sleep(0.2)

        try:
            base_url = "http://127.0.0.1:8099"

            # 1. Test GET /
            req = urllib.request.Request(base_url)
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content = resp.read().decode("utf-8")
                self.assertIn("<title>Mumble-Butler Dashboard</title>", content)
                self.assertIn("htmx.org", content)

            # 2. Test GET /api/status
            req = urllib.request.Request(f"{base_url}/api/status")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content = resp.read().decode("utf-8")
                self.assertIn("Bot Health & Metrics", content)
                self.assertIn("Uptime", content)

            # 3. Test GET /api/config
            req = urllib.request.Request(f"{base_url}/api/config")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content = resp.read().decode("utf-8")
                self.assertIn("SERVER_PORT", content)
                self.assertIn('hx-post="/api/config/update"', content)

            # 4. Test POST /api/config/update
            data = urllib.parse.urlencode({"key": "OLLAMA_MODEL", "value": "test-gemma"}).encode("utf-8")
            req = urllib.request.Request(f"{base_url}/api/config/update", data=data, method="POST")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content = resp.read().decode("utf-8")
                self.assertIn("toast-success", content)
                self.assertIn("OLLAMA_MODEL", content)

            self.assertEqual(config.OLLAMA_MODEL, "test-gemma")

            # 5. Test POST /api/bot/action
            data = urllib.parse.urlencode({"action": "toggle_listen"}).encode("utf-8")
            req = urllib.request.Request(f"{base_url}/api/bot/action", data=data, method="POST")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                content = resp.read().decode("utf-8")
                self.assertIn("disabled", content)

            self.assertFalse(bot.listening_enabled)

            # 6. Test GET /api/tts
            bot.voice = type("DummyVoice", (), {"generate_pcm": lambda self, text, voice_id=None, model_type=None: b"\x00\x00" * 4800})()
            req = urllib.request.Request(f"{base_url}/api/tts?text=Hello+world&format=json")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["status"], "ok")
                self.assertEqual(data["text"], "Hello world")
                self.assertIn("audio_base64", data)

            # 7. Test POST /api/tts returning WAV
            post_data = urllib.parse.urlencode({"text": "Hei suomi", "format": "wav"}).encode("utf-8")
            req = urllib.request.Request(f"{base_url}/api/tts", data=post_data, method="POST")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers.get("Content-Type"), "audio/wav")
                wav_content = resp.read()
                self.assertTrue(wav_content.startswith(b"RIFF"))

            # 8. Test GET /api/tts default format (Ogg Opus or fallback)
            req = urllib.request.Request(f"{base_url}/api/tts?text=Terve")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn(resp.headers.get("Content-Type"), ["audio/ogg", "audio/wav"])

        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
