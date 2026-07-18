"""Tests for botamusique music command forwarding."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from handlers.text import TextHandler
from handlers.voice import VoiceHandler


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def _load_bot_module():
    module_name = "bot_under_test"
    if module_name in sys.modules:
        del sys.modules[module_name]

    fake_pymumble = types.ModuleType("pymumble_py3")
    fake_pymumble.Mumble = object

    fake_utils = types.ModuleType("utils")
    fake_utils.patch_ssl = lambda: None

    fake_brain = types.ModuleType("modules.brain")
    fake_brain.Brain = type("Brain", (), {})

    fake_ears = types.ModuleType("modules.ears")
    fake_ears.Ear = type("Ear", (), {})

    fake_voice = types.ModuleType("modules.voice")
    fake_voice.Voice = type("Voice", (), {})

    fake_audio_manager = types.ModuleType("modules.audio_manager")
    fake_audio_manager.AudioManager = type("AudioManager", (), {})


    fake_text = types.ModuleType("handlers.text")
    fake_text.TextHandler = type("TextHandler", (), {})

    fake_voice_handler = types.ModuleType("handlers.voice")
    fake_voice_handler.VoiceHandler = type("VoiceHandler", (), {})

    spec = importlib.util.spec_from_file_location(module_name, BOT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    patched_modules = {
        "pymumble_py3": fake_pymumble,
        "utils": fake_utils,
        "modules.brain": fake_brain,
        "modules.ears": fake_ears,
        "modules.voice": fake_voice,
        "modules.audio_manager": fake_audio_manager,
        "handlers.text": fake_text,
        "handlers.voice": fake_voice_handler,
    }
    original_modules = {}
    try:
        for name, fake_module in patched_modules.items():
            original_modules[name] = sys.modules.get(name)
            sys.modules[name] = fake_module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _make_message(text):
    return SimpleNamespace(actor=2, message=text)


class _FakeUsers(dict):
    myself_session = 1


class MusicCommandForwardingTests(unittest.TestCase):
    def test_bot_methods_forward_botamusique_commands(self):
        bot_module = _load_bot_module()
        madness_bot = bot_module.MadnessBot.__new__(bot_module.MadnessBot)
        sent = []
        madness_bot.send_chat = sent.append

        self.assertEqual(madness_bot.play("lofi mix"), "!yplay lofi mix")
        self.assertEqual(madness_bot.play_file("local track"), "!file local track")
        self.assertEqual(madness_bot.resume_music(), "!play")
        self.assertEqual(madness_bot.request_now_playing(), "!np")
        self.assertEqual(madness_bot.request_queue(), "!queue")
        self.assertEqual(sent, ["!yplay lofi mix", "!file local track", "!play", "!np", "!queue"])

    def test_text_handler_forwards_status_commands(self):
        bot = MagicMock()
        bot.mumble = SimpleNamespace(users=_FakeUsers({2: {"name": "Tester"}}))
        handler = TextHandler(bot)

        handler.handle(_make_message("?now"))
        handler.handle(_make_message("?queue"))

        bot.request_now_playing.assert_called_once_with()
        bot.request_queue.assert_called_once_with()

    def test_voice_handler_uses_play_file_for_file_requests(self):
        bot = MagicMock()
        bot.chime_pcm = None
        bot.mumble = None
        bot.listening_enabled = True
        handler = VoiceHandler(bot)

        handled = handler.handle("Tester", "obama file local track")

        self.assertTrue(handled)
        bot.play_file.assert_called_once_with("local track")

    def test_stop_speaking_clears_pending_tts_and_audio_buffer(self):
        bot_module = _load_bot_module()
        madness_bot = bot_module.MadnessBot.__new__(bot_module.MadnessBot)
        madness_bot.speech_generation = 0
        madness_bot.loop = SimpleNamespace(call_soon_threadsafe=lambda func, *args: func(*args))
        class FakeAsyncQueue:
            def __init__(self):
                self.items = []

            def put_nowait(self, item):
                self.items.append(item)

            def get_nowait(self):
                if not self.items:
                    raise bot_module.asyncio.QueueEmpty()
                return self.items.pop(0)

            def task_done(self):
                return None

            def empty(self):
                return not self.items

        madness_bot.queue = FakeAsyncQueue()
        madness_bot.queue.put_nowait((0, "one"))
        madness_bot.queue.put_nowait((0, "two"))
        sound_output = SimpleNamespace(clear_buffer=MagicMock())
        madness_bot.mumble = SimpleNamespace(sound_output=sound_output)

        madness_bot.stop_speaking()

        self.assertEqual(madness_bot.speech_generation, 1)
        self.assertTrue(madness_bot.queue.empty())
        sound_output.clear_buffer.assert_called_once_with()

    def test_say_async_chunking(self):
        bot_module = _load_bot_module()
        madness_bot = bot_module.MadnessBot.__new__(bot_module.MadnessBot)
        madness_bot.speech_generation = 12
        
        queued_items = []
        def fake_call_soon_threadsafe(func, *args):
            func(*args)
            
        madness_bot.loop = SimpleNamespace(call_soon_threadsafe=fake_call_soon_threadsafe)
        
        class FakeAsyncQueue:
            def put_nowait(self, item):
                queued_items.append(item)
                
        madness_bot.queue = FakeAsyncQueue()
        
        test_text = "Hello! This is a test.   How are you doing today?\nLet's check this out."
        madness_bot.say_async(test_text, user="Tester")
        
        expected = [
            (12, "Hello!", "Tester"),
            (12, "This is a test.", "Tester"),
            (12, "How are you doing today?", "Tester"),
            (12, "Let's check this out.", "Tester")
        ]
        self.assertEqual(queued_items, expected)


if __name__ == "__main__":
    unittest.main()
