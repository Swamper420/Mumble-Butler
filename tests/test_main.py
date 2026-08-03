import unittest
import config
from utils import get_resample_indices, resample_int16
import numpy as np

class TestMainSmoke(unittest.TestCase):
    def test_config_defaults(self):
        self.assertEqual(config.BOT_USERNAME, "Obama")
        self.assertTrue(hasattr(config, "TTS_VOICE"))
        self.assertFalse(hasattr(config, "KOKORO_VOICE_ID"))

    def test_utils_resample_caching(self):
        idx1 = get_resample_indices(4800, 48000, 16000)
        idx2 = get_resample_indices(4800, 48000, 16000)
        self.assertIs(idx1, idx2)

        data = np.zeros(4800, dtype=np.int16)
        resampled = resample_int16(data, 48000, 16000)
        self.assertEqual(len(resampled), 1600)

if __name__ == "__main__":
    unittest.main()
