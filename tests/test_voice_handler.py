"""Tests for VoiceHandler shut-up keyword behaviour."""
import unittest
from unittest.mock import MagicMock, patch

import config
from handlers.voice import VoiceHandler


def _make_handler():
    """Return a VoiceHandler with a mocked bot."""
    bot = MagicMock()
    bot.chime_pcm = None
    bot.mumble = None
    bot.listening_enabled = True
    handler = VoiceHandler(bot)
    return handler, bot


class TestShutupKeywordHandling(unittest.TestCase):
    """Ensure the shut-up keyword stops speech without disabling listening."""

    def test_shutup_stops_speaking(self):
        handler, bot = _make_handler()
        # "obama shut up" — activation keyword + shut-up keyword
        result = handler.handle("TestUser", "obama shut up")
        self.assertTrue(result)
        self.assertTrue(bot.listening_enabled)
        bot.stop_speaking.assert_called_once_with()
        bot.say_async.assert_not_called()

    def test_shutup_variant_be_quiet(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama be quiet")
        self.assertTrue(result)
        self.assertTrue(bot.listening_enabled)
        bot.stop_speaking.assert_called_once_with()

    def test_no_activation_keyword_no_shutup(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "shut up")
        self.assertFalse(result)
        self.assertTrue(bot.listening_enabled)
        bot.stop_speaking.assert_not_called()

    def test_normal_command_does_not_disable_listening(self):
        handler, bot = _make_handler()
        bot.brain = MagicMock()
        bot.brain.generate_response.return_value = "Hello!"
        handler.handle("TestUser", "obama hello there")
        self.assertTrue(bot.listening_enabled)
        bot.stop_speaking.assert_not_called()


if __name__ == "__main__":
    unittest.main()
