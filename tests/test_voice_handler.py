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

    def test_reminder_command_schedules_minutes_and_confirms(self):
        handler, bot = _make_handler()

        result = handler.handle(
            "TestUser",
            "obama remind me in 20 minutes about the fire place",
        )

        self.assertTrue(result)
        bot.schedule_reminder.assert_called_once_with(20 * 60, "the fire place")
        bot.say_async.assert_called_once_with("I will remind you in 20 minutes.")

    def test_reminder_command_supports_seconds_and_hours(self):
        cases = [
            ("obama remind me in 30 seconds to stretch", 30, "stretch", "I will remind you in 30 seconds."),
            ("obama remind me in 2 hours about laundry", 2 * 60 * 60, "laundry", "I will remind you in 2 hours."),
        ]

        for spoken_text, expected_seconds, expected_message, expected_confirmation in cases:
            with self.subTest(spoken_text=spoken_text):
                handler, bot = _make_handler()

                result = handler.handle("TestUser", spoken_text)

                self.assertTrue(result)
                bot.schedule_reminder.assert_called_once_with(expected_seconds, expected_message)
                bot.say_async.assert_called_once_with(expected_confirmation)


if __name__ == "__main__":
    unittest.main()
