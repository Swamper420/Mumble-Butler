import unittest
from unittest.mock import MagicMock, patch

import config
from modules.audio_buffer import UserVoiceStream
from modules.audio_manager import AudioManager


class TestWakewordFixes(unittest.TestCase):
    def test_user_voice_stream_resets_model_and_state(self):
        fake_detector = MagicMock()
        fake_stream_model = MagicMock()
        fake_detector.enabled = True
        fake_detector.create_stream_model.return_value = fake_stream_model

        fake_bot = MagicMock()
        fake_bot.wakeword_detector = fake_detector

        stream = UserVoiceStream("TestUser", fake_bot)
        fake_detector.create_stream_model.assert_called_once()
        self.assertEqual(stream.wakeword_model, fake_stream_model)

        # Set some state
        stream.wakeword_detected = True
        stream.accumulated_16k_bytes.extend(b"1234")
        stream.consecutive_hits = 3

        # Call extract_audio which resets state
        stream.extract_audio()

        self.assertFalse(stream.wakeword_detected)
        self.assertEqual(len(stream.accumulated_16k_bytes), 0)
        self.assertEqual(stream.consecutive_hits, 0)
        fake_stream_model.reset.assert_called_once()

    def test_consecutive_hits_required_for_detection(self):
        fake_model = MagicMock()
        fake_detector = MagicMock()
        fake_detector.enabled = True
        fake_detector.create_stream_model.return_value = fake_model

        fake_bot = MagicMock()
        fake_bot.wakeword_detector = fake_detector

        manager = AudioManager(fake_bot)
        stream = UserVoiceStream("TestUser", fake_bot)
        stream.wakeword_model = fake_model

        # Scenario 1: First chunk scores high (0.8 >= 0.5 threshold), but only 1 hit
        fake_model.predict.return_value = {"model_1": 0.8}
        pcm_chunk_1 = bytes(4800 * 2)  # 100ms 48k 16-bit audio -> ~33.3ms 16k = enough bytes when accumulated
        
        # Simulate processing single chunk
        # Set config threshold and min hits
        with patch.object(config, "WAKEWORD_THRESHOLD", 0.5), \
             patch.object(config, "WAKEWORD_CONSECUTIVE_HITS", 2):
            
            # Feed 1280 samples (2560 bytes) directly to _process_wakeword
            # Generate 48k PCM data that downsamples to 2560 bytes (1280 samples) @ 16k
            # 1280 samples @ 16k = 3840 samples @ 48k -> 7680 bytes
            pcm_data = bytes(7680)
            manager._process_wakeword(stream, pcm_data)

            self.assertFalse(stream.wakeword_detected)
            self.assertEqual(stream.consecutive_hits, 1)

            # Second consecutive chunk also scores high -> Should now trigger detection!
            manager._process_wakeword(stream, pcm_data)
            self.assertTrue(stream.wakeword_detected)

    def test_non_consecutive_hit_resets_counter(self):
        fake_model = MagicMock()
        fake_detector = MagicMock()
        fake_detector.enabled = True
        fake_detector.create_stream_model.return_value = fake_model

        fake_bot = MagicMock()
        fake_bot.wakeword_detector = fake_detector

        manager = AudioManager(fake_bot)
        stream = UserVoiceStream("TestUser", fake_bot)
        stream.wakeword_model = fake_model

        pcm_data = bytes(7680)

        with patch.object(config, "WAKEWORD_THRESHOLD", 0.5), \
             patch.object(config, "WAKEWORD_CONSECUTIVE_HITS", 2):

            # Chunk 1: High score (consecutive_hits -> 1)
            fake_model.predict.return_value = {"model_1": 0.8}
            manager._process_wakeword(stream, pcm_data)
            self.assertEqual(stream.consecutive_hits, 1)
            self.assertFalse(stream.wakeword_detected)

            # Chunk 2: Low score (consecutive_hits -> resets to 0)
            fake_model.predict.return_value = {"model_1": 0.2}
            manager._process_wakeword(stream, pcm_data)
            self.assertEqual(stream.consecutive_hits, 0)
            self.assertFalse(stream.wakeword_detected)


if __name__ == "__main__":
    unittest.main()
