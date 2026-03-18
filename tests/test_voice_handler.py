"""Tests for VoiceHandler shut-up keyword behaviour."""
import unittest
from unittest.mock import MagicMock, patch, call

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
    """Ensure the shut-up keyword disables listening."""

    def test_shutup_disables_listening(self):
        handler, bot = _make_handler()
        # "obama shut up" — activation keyword + shut-up keyword
        result = handler.handle("TestUser", "obama shut up")
        self.assertTrue(result)
        self.assertFalse(bot.listening_enabled)
        bot.say_async.assert_called_once_with("Fine, I'll be quiet.")

    def test_shutup_clears_voice_queue(self):
        handler, bot = _make_handler()
        handler.handle("TestUser", "obama shut up")
        bot.clear_voice_queue.assert_called_once()

    def test_shutup_stops_music(self):
        handler, bot = _make_handler()
        handler.handle("TestUser", "obama shut up")
        bot.stop_music.assert_called_once()

    def test_shutup_variant_be_quiet(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama be quiet")
        self.assertTrue(result)
        self.assertFalse(bot.listening_enabled)

    def test_no_activation_keyword_no_shutup(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "shut up")
        self.assertFalse(result)
        self.assertTrue(bot.listening_enabled)

    def test_normal_command_does_not_disable_listening(self):
        handler, bot = _make_handler()
        bot.brain = MagicMock()
        bot.brain.generate_response.return_value = "Hello!"
        handler.handle("TestUser", "obama hello there")
        self.assertTrue(bot.listening_enabled)


class TestVoiceCommandRouting(unittest.TestCase):
    """Ensure voice commands are correctly routed to bot methods."""

    def test_stop_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama stop")
        self.assertTrue(result)
        bot.stop_music.assert_called_once()

    def test_skip_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama skip")
        self.assertTrue(result)
        bot.skip.assert_called_once()

    def test_resume_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama resume")
        self.assertTrue(result)
        bot.resume_music.assert_called_once()

    def test_volume_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama volume 50")
        self.assertTrue(result)
        bot.set_volume.assert_called_once_with(50)

    def test_play_specific_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama play something cool")
        self.assertTrue(result)
        bot.play.assert_called_once_with("something cool")

    def test_mode_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama mode autoplay")
        self.assertTrue(result)
        bot.set_mode.assert_called_once_with("autoplay")

    def test_forget_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama forget")
        self.assertTrue(result)
        bot.brain.reset_memory.assert_called_once()

    def test_repeat_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama repeat 3")
        self.assertTrue(result)
        bot.repeat_music.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
