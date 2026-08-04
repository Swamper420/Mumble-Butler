"""Tests for VoiceHandler shut-up keyword behaviour."""
import unittest
from unittest.mock import MagicMock

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

    def test_shutup_without_activation_keyword(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "shut up")
        self.assertTrue(result)
        self.assertTrue(bot.listening_enabled)
        bot.stop_speaking.assert_called_once_with()

    def test_command_without_activation_keyword(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "hello there")
        self.assertTrue(result)
        self.assertTrue(bot.listening_enabled)
        bot.say_stream.assert_called_once_with("Käyttäjä TestUser sanoo: hello there", user="TestUser")

    def test_normal_command_does_not_disable_listening(self):
        handler, bot = _make_handler()
        bot.brain = MagicMock()
        bot.brain.generate_response.return_value = "Hei!"
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
        bot.say_async.assert_called_once_with("Muistutan sinua 20 minutes kuluttua.")

    def test_reminder_command_supports_seconds_and_hours(self):
        cases = [
            ("obama remind me in 30 seconds to stretch", 30, "stretch", "Muistutan sinua 30 seconds kuluttua."),
            ("obama remind me in 2 hours about laundry", 2 * 60 * 60, "laundry", "Muistutan sinua 2 hours kuluttua."),
        ]

        for spoken_text, expected_seconds, expected_message, expected_confirmation in cases:
            with self.subTest(spoken_text=spoken_text):
                handler, bot = _make_handler()

                result = handler.handle("TestUser", spoken_text)

                self.assertTrue(result)
                bot.schedule_reminder.assert_called_once_with(expected_seconds, expected_message)

    def test_finnish_reminder_command(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama muistuta minua 10 minuutin kuluttua asiasta sauna")
        self.assertTrue(result)
        bot.schedule_reminder.assert_called_once_with(10 * 60, "sauna")
        bot.say_async.assert_called_once_with("Muistutan sinua 10 minuutin kuluttua.")

    def test_best_player_does_not_trigger_play(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama who is the best player")
        self.assertTrue(result)
        bot.play.assert_not_called()
        bot.say_stream.assert_called_once_with("Käyttäjä TestUser sanoo: who is the best player", user="TestUser")

    def test_word_boundary_prevents_false_positives(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama tell me about this profile and musician")
        self.assertTrue(result)
        bot.play.assert_not_called()
        bot.play_file.assert_not_called()
        bot.say_stream.assert_called_once_with("Käyttäjä TestUser sanoo: tell me about this profile and musician", user="TestUser")

    def test_play_command_with_query_executes_music_play(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama play hotel california")
        self.assertTrue(result)
        bot.play.assert_called_once_with("hotel california")
        bot.say_stream.assert_not_called()

    def test_finnish_soita_command_executes_music_play(self):
        handler, bot = _make_handler()
        result = handler.handle("TestUser", "obama soita darude sandstorm")
        self.assertTrue(result)
        bot.play.assert_called_once_with("darude sandstorm")
        bot.say_stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()

