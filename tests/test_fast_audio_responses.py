import unittest
from unittest.mock import MagicMock, patch
import config
from bot import MadnessBot
from handlers.voice import VoiceHandler


class TestFastAudioResponses(unittest.TestCase):

    def setUp(self):
        self.original_enabled = getattr(config, "FAST_AUDIO_RESPONSES_ENABLED", False)

    def tearDown(self):
        config.FAST_AUDIO_RESPONSES_ENABLED = self.original_enabled

    def test_config_defaults(self):
        """Test default config values for fast audio responses."""
        self.assertIsInstance(config.FAST_AUDIO_RESPONSES_ENABLED, bool)
        self.assertIsInstance(config.FAST_WAKEWORD_RESPONSES, list)
        self.assertGreater(len(config.FAST_WAKEWORD_RESPONSES), 0)
        self.assertIsInstance(config.FAST_ACTION_CONFIRMATIONS, dict)
        self.assertIn("MUSIC", config.FAST_ACTION_CONFIRMATIONS)
        self.assertIn("SEARCH", config.FAST_ACTION_CONFIRMATIONS)

    @patch("bot.Voice")
    @patch("bot.Brain")
    @patch("bot.Ear")
    @patch("bot.AudioManager")
    @patch("bot.WakewordDetector")
    @patch("bot.BotWebServer")
    def test_precache_on_boot_disabled(self, mock_web, mock_wake, mock_audio, mock_ear, mock_brain, mock_voice_cls):
        """When FAST_AUDIO_RESPONSES_ENABLED is False, no PCMs are precached."""
        config.FAST_AUDIO_RESPONSES_ENABLED = False
        bot = MadnessBot()
        self.assertEqual(len(bot.precached_wakeword_pcms), 0)
        self.assertEqual(len(bot.precached_action_pcms), 0)

    @patch("bot.Voice")
    @patch("bot.Brain")
    @patch("bot.Ear")
    @patch("bot.AudioManager")
    @patch("bot.WakewordDetector")
    @patch("bot.BotWebServer")
    def test_precache_on_boot_enabled(self, mock_web, mock_wake, mock_audio, mock_ear, mock_brain, mock_voice_cls):
        """When FAST_AUDIO_RESPONSES_ENABLED is True, PCMs are pre-generated on boot."""
        config.FAST_AUDIO_RESPONSES_ENABLED = True
        mock_voice_inst = mock_voice_cls.return_value
        mock_voice_inst.generate_pcm.side_effect = lambda text: f"pcm_for_{text}".encode("utf-8")

        bot = MadnessBot()

        self.assertGreater(len(bot.precached_wakeword_pcms), 0)
        self.assertGreater(len(bot.precached_action_pcms), 0)
        self.assertIn("MUSIC", bot.precached_action_pcms)

    def test_play_ack_sound_fallback_to_chime(self):
        """Test play_ack_sound falls back to chime_pcm when fast responses are disabled."""
        bot = MagicMock()
        bot.chime_pcm = b"chime_raw_bytes"
        bot.precached_wakeword_pcms = []
        bot.mumble = MagicMock()
        
        config.FAST_AUDIO_RESPONSES_ENABLED = False

        # Bind method to mock bot
        MadnessBot.play_ack_sound(bot)

        bot.mumble.sound_output.add_sound.assert_called_once_with(b"chime_raw_bytes")

    def test_play_ack_sound_uses_precached_wakeword(self):
        """Test play_ack_sound plays precached wakeword response when enabled."""
        bot = MagicMock()
        bot.chime_pcm = b"chime_raw_bytes"
        bot.precached_wakeword_pcms = [b"wake_response_1_pcm"]
        bot.mumble = MagicMock()

        config.FAST_AUDIO_RESPONSES_ENABLED = True

        MadnessBot.play_ack_sound(bot)

        bot.mumble.sound_output.add_sound.assert_called_once_with(b"wake_response_1_pcm")

    def test_play_action_confirmation(self):
        """Test play_action_confirmation plays correct action PCM."""
        bot = MagicMock()
        bot.precached_action_pcms = {
            "MUSIC": b"fetching_song_pcm",
            "SEARCH": b"searching_info_pcm"
        }
        bot.mumble = MagicMock()

        config.FAST_AUDIO_RESPONSES_ENABLED = True

        MadnessBot.play_action_confirmation(bot, "MUSIC")
        bot.mumble.sound_output.add_sound.assert_called_with(b"fetching_song_pcm")

        bot.mumble.sound_output.add_sound.reset_mock()
        MadnessBot.play_action_confirmation(bot, "SEARCH")
        bot.mumble.sound_output.add_sound.assert_called_with(b"searching_info_pcm")

    def test_voice_handler_triggers_action_confirmations(self):
        """Test VoiceHandler calls play_action_confirmation for every command trigger."""
        bot = MagicMock()
        bot.listening_enabled = True
        handler = VoiceHandler(bot)

        # Test volume command
        handler.handle("TestUser", "obama volume 50")
        bot.play_action_confirmation.assert_called_with("VOLUME")

        # Test skip command
        bot.play_action_confirmation.reset_mock()
        handler.handle("TestUser", "obama skip")
        bot.play_action_confirmation.assert_called_with("SKIP")

        # Test status command
        bot.play_action_confirmation.reset_mock()
        bot.get_status.return_value = {"Uptime": "1m", "LLM": "ok", "Listening": "yes"}
        handler.handle("TestUser", "obama status")
        bot.play_action_confirmation.assert_called_with("STATUS")


if __name__ == "__main__":
    unittest.main()
