import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import config
from bot import MadnessBot
from handlers.voice import VoiceHandler


class TestFastAudioResponses(unittest.TestCase):

    def setUp(self):
        self.original_enabled = getattr(config, "FAST_AUDIO_RESPONSES_ENABLED", False)
        self.original_cache_dir = getattr(config, "FAST_AUDIO_CACHE_DIR", "data/precached_audio")
        self.temp_cache_dir = tempfile.mkdtemp()
        config.FAST_AUDIO_CACHE_DIR = self.temp_cache_dir

    def tearDown(self):
        config.FAST_AUDIO_RESPONSES_ENABLED = self.original_enabled
        config.FAST_AUDIO_CACHE_DIR = self.original_cache_dir
        if os.path.exists(self.temp_cache_dir):
            shutil.rmtree(self.temp_cache_dir, ignore_errors=True)

    def test_config_defaults(self):
        """Test default config values for fast audio responses."""
        self.assertIsInstance(config.FAST_AUDIO_RESPONSES_ENABLED, bool)
        self.assertIsInstance(config.FAST_AUDIO_CACHE_DIR, str)
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
        self.assertEqual(len(bot.precached_volume_pcms), 0)

    @patch("bot.Voice")
    @patch("bot.Brain")
    @patch("bot.Ear")
    @patch("bot.AudioManager")
    @patch("bot.WakewordDetector")
    @patch("bot.BotWebServer")
    def test_precache_on_boot_enabled_and_disk_saving(self, mock_web, mock_wake, mock_audio, mock_ear, mock_brain, mock_voice_cls):
        """When FAST_AUDIO_RESPONSES_ENABLED is True, PCMs are pre-generated and saved to disk."""
        config.FAST_AUDIO_RESPONSES_ENABLED = True
        mock_voice_inst = mock_voice_cls.return_value
        mock_voice_inst.current_voice_id = "michael"
        mock_voice_inst.get_available_voices.return_value = ["michael"]
        mock_voice_inst.generate_pcm.side_effect = lambda text, voice_id=None: f"pcm_{voice_id}_{text}".encode("utf-8")

        bot = MadnessBot()

        # Verify memory cache structure
        self.assertIn("michael", bot.precached_wakeword_pcms)
        self.assertGreater(len(bot.precached_wakeword_pcms["michael"]), 0)

        self.assertIn("michael", bot.precached_action_pcms)
        self.assertIn("MUSIC", bot.precached_action_pcms["michael"])

        self.assertIn("michael", bot.precached_volume_pcms)
        self.assertEqual(len(bot.precached_volume_pcms["michael"]), 101)  # 0 to 100
        self.assertIn(50, bot.precached_volume_pcms["michael"])

        # Verify disk persistence
        vol_50_file = os.path.join(self.temp_cache_dir, "michael", "volume", "50.pcm")
        self.assertTrue(os.path.exists(vol_50_file))
        with open(vol_50_file, "rb") as f:
            self.assertEqual(f.read(), b"pcm_michael_Volume 50")

    @patch("bot.Voice")
    @patch("bot.Brain")
    @patch("bot.Ear")
    @patch("bot.AudioManager")
    @patch("bot.WakewordDetector")
    @patch("bot.BotWebServer")
    def test_precache_disk_loading(self, mock_web, mock_wake, mock_audio, mock_ear, mock_brain, mock_voice_cls):
        """On subsequent boot up, PCMs are loaded directly from disk without calling generate_pcm."""
        config.FAST_AUDIO_RESPONSES_ENABLED = True
        mock_voice_inst = mock_voice_cls.return_value
        mock_voice_inst.current_voice_id = "michael"
        mock_voice_inst.get_available_voices.return_value = ["michael"]
        mock_voice_inst.generate_pcm.side_effect = lambda text, voice_id=None: f"pcm_{voice_id}_{text}".encode("utf-8")

        # 1st boot: generates and saves to disk
        bot1 = MadnessBot()
        initial_call_count = mock_voice_inst.generate_pcm.call_count
        self.assertGreater(initial_call_count, 0)

        # Reset call count mock
        mock_voice_inst.generate_pcm.reset_mock()

        # 2nd boot: should load from disk, generate_pcm should not be called
        bot2 = MadnessBot()
        self.assertEqual(mock_voice_inst.generate_pcm.call_count, 0)
        self.assertIn(50, bot2.precached_volume_pcms["michael"])
        self.assertEqual(bot2.precached_volume_pcms["michael"][50], b"pcm_michael_Volume 50")

    def test_play_ack_sound_fallback_to_chime(self):
        """Test play_ack_sound falls back to chime_pcm when fast responses are disabled."""
        bot = MagicMock()
        bot.chime_pcm = b"chime_raw_bytes"
        bot.precached_wakeword_pcms = {}
        bot.mumble = MagicMock()
        
        config.FAST_AUDIO_RESPONSES_ENABLED = False

        MadnessBot.play_ack_sound(bot)

        bot.mumble.sound_output.add_sound.assert_called_once_with(b"chime_raw_bytes")

    def test_play_ack_sound_uses_precached_wakeword(self):
        """Test play_ack_sound plays precached wakeword response when enabled."""
        bot = MagicMock()
        bot.chime_pcm = b"chime_raw_bytes"
        bot.voice = MagicMock()
        bot.voice.current_voice_id = "michael"
        bot.precached_wakeword_pcms = {"michael": [b"wake_response_1_pcm"]}
        bot.mumble = MagicMock()

        config.FAST_AUDIO_RESPONSES_ENABLED = True

        MadnessBot.play_ack_sound(bot)

        bot.mumble.sound_output.add_sound.assert_called_once_with(b"wake_response_1_pcm")

    def test_play_action_confirmation(self):
        """Test play_action_confirmation plays correct action PCM."""
        bot = MagicMock()
        bot.voice = MagicMock()
        bot.voice.current_voice_id = "michael"
        bot.precached_action_pcms = {
            "michael": {
                "MUSIC": b"fetching_song_pcm",
                "SEARCH": b"searching_info_pcm"
            }
        }
        bot.mumble = MagicMock()

        config.FAST_AUDIO_RESPONSES_ENABLED = True

        MadnessBot.play_action_confirmation(bot, "MUSIC")
        bot.mumble.sound_output.add_sound.assert_called_with(b"fetching_song_pcm")

        bot.mumble.sound_output.add_sound.reset_mock()
        MadnessBot.play_action_confirmation(bot, "SEARCH")
        bot.mumble.sound_output.add_sound.assert_called_with(b"searching_info_pcm")

    def test_play_action_confirmation_volume_level(self):
        """Test play_action_confirmation with volume level plays specific volume PCM."""
        bot = MagicMock()
        bot.voice = MagicMock()
        bot.voice.current_voice_id = "michael"
        bot.precached_volume_pcms = {
            "michael": {
                50: b"volume_50_pcm"
            }
        }
        bot.precached_action_pcms = {
            "michael": {
                "VOLUME": b"adjusting_volume_generic_pcm"
            }
        }
        bot.mumble = MagicMock()

        config.FAST_AUDIO_RESPONSES_ENABLED = True

        # Test specific volume level
        MadnessBot.play_action_confirmation(bot, "VOLUME", level=50)
        bot.mumble.sound_output.add_sound.assert_called_with(b"volume_50_pcm")

        # Test fallback when level is None
        bot.mumble.sound_output.add_sound.reset_mock()
        MadnessBot.play_action_confirmation(bot, "VOLUME")
        bot.mumble.sound_output.add_sound.assert_called_with(b"adjusting_volume_generic_pcm")

    def test_voice_handler_triggers_action_confirmations(self):
        """Test VoiceHandler calls play_action_confirmation for every command trigger including volume level."""
        bot = MagicMock()
        bot.listening_enabled = True
        handler = VoiceHandler(bot)

        # Test volume command with level
        handler.handle("TestUser", "obama volume 50")
        bot.play_action_confirmation.assert_called_with("VOLUME", level=50)

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
