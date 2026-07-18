import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace
import asyncio
import os

from handlers.text import TextHandler
import config

class _FakeUsers(dict):
    myself_session = 1

def _make_message(text):
    return SimpleNamespace(actor=2, message=text)

class TestSaysaveCommand(unittest.TestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.mumble = SimpleNamespace(users=_FakeUsers({2: {"name": "Tester"}}))
        self.handler = TextHandler(self.bot)

    def test_saysave_routing(self):
        msg = _make_message("?saysave Hello world!")
        self.handler.handle(msg)
        self.bot.saysave_async.assert_called_once_with("Hello world!", user="Tester")

    def test_saysave_no_arg(self):
        msg = _make_message("?saysave")
        self.handler.handle(msg)
        self.bot.saysave_async.assert_not_called()
        self.bot.send_chat.assert_called_once()
        self.assertIn("Usage", self.bot.send_chat.call_args[0][0])

    def test_saysave_too_long(self):
        msg = _make_message("?saysave " + ("a" * 1001))
        self.handler.handle(msg)
        self.bot.saysave_async.assert_not_called()
        self.bot.send_chat.assert_called_once()
        self.assertIn("Error", self.bot.send_chat.call_args[0][0])


class TestSaysaveBotLogic(unittest.IsolatedAsyncioTestCase):
    @patch("asyncio.create_subprocess_exec")
    @patch("os.makedirs")
    async def test_async_saysave_success(self, mock_makedirs, mock_create_subprocess):
        # We need a bot instance
        from bot import MadnessBot
        # Use patch to mock bot initialization components so it doesn't fail
        with patch.object(MadnessBot, "__init__", lambda self: None):
            bot = MadnessBot()
            bot.loop = asyncio.get_event_loop()
            bot.executor = None
            bot.logger = MagicMock()
            bot.voice = MagicMock()
            bot.voice.generate_pcm = MagicMock(return_value=b"fake_pcm_data")
            bot.send_chat = MagicMock()
            bot.say_async = MagicMock()

            # Mock subprocess run
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (None, None)
            mock_proc.returncode = 0
            mock_create_subprocess.return_value = mock_proc

            # Run the _async_saysave method
            await bot._async_saysave("Hello World", "Tester")

            # Check that say_async was called to play the speech locally
            bot.say_async.assert_called_once_with("Hello World", user="Tester")

            # Check that generate_pcm was called (using run_in_executor mock)
            bot.voice.generate_pcm.assert_called_once_with("Hello World", None)

            # Check that ffmpeg was called
            mock_create_subprocess.assert_called_once()
            args, kwargs = mock_create_subprocess.call_args
            self.assertEqual(args[0], "ffmpeg")
            self.assertIn("-c:a", args)
            self.assertIn("aac", args)

            # Check that send_chat was called with the success message
            bot.send_chat.assert_called_once()
            self.assertIn("Voiceline saved to", bot.send_chat.call_args[0][0])
            self.assertIn(".m4a", bot.send_chat.call_args[0][0])

    @patch("asyncio.create_subprocess_exec")
    @patch("os.makedirs")
    async def test_async_saysave_no_pcm(self, mock_makedirs, mock_create_subprocess):
        from bot import MadnessBot
        with patch.object(MadnessBot, "__init__", lambda self: None):
            bot = MadnessBot()
            bot.loop = asyncio.get_event_loop()
            bot.executor = None
            bot.logger = MagicMock()
            bot.voice = MagicMock()
            bot.voice.generate_pcm = MagicMock(return_value=None)
            bot.send_chat = MagicMock()
            bot.say_async = MagicMock()

            await bot._async_saysave("Hello World", "Tester")

            # Check that we reported an error and did not run ffmpeg
            bot.send_chat.assert_called_once_with("<b>Error:</b> Speech generation returned no audio data.")
            mock_create_subprocess.assert_not_called()
