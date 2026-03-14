from types import SimpleNamespace
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

if "numpy" not in sys.modules:
    fake_numpy = types.ModuleType("numpy")
    fake_numpy.ndarray = list
    sys.modules["numpy"] = fake_numpy

from modules import ears


class EarTranscribeTests(unittest.TestCase):
    @patch("modules.ears.resample_audio", return_value=[0.1])
    @patch("modules.ears.pcm_to_float", return_value=[0.1])
    def test_transcribe_passes_configured_language(self, _pcm_to_float, _resample_audio):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([SimpleNamespace(text="hei maailma")], None)

        with patch.object(ears, "STT_AVAILABLE", True), patch.object(ears, "WhisperModel", return_value=fake_model, create=True), patch.object(ears.config, "WHISPER_LANGUAGE", "fi"):
            ear = ears.Ear()
            text = ear.transcribe(b"\x00\x00")

        self.assertEqual(text, "hei maailma")
        _, kwargs = fake_model.transcribe.call_args
        self.assertEqual(kwargs["language"], "fi")
        self.assertEqual(kwargs["beam_size"], 5)

    @patch("modules.ears.resample_audio", return_value=[0.1])
    @patch("modules.ears.pcm_to_float", return_value=[0.1])
    def test_transcribe_allows_auto_language_when_config_is_none(self, _pcm_to_float, _resample_audio):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([SimpleNamespace(text="hello")], None)

        with patch.object(ears, "STT_AVAILABLE", True), patch.object(ears, "WhisperModel", return_value=fake_model, create=True), patch.object(ears.config, "WHISPER_LANGUAGE", None):
            ear = ears.Ear()
            ear.transcribe(b"\x00\x00")

        _, kwargs = fake_model.transcribe.call_args
        self.assertIsNone(kwargs["language"])

    def test_transcribe_returns_empty_string_when_model_unavailable(self):
        with patch.object(ears, "STT_AVAILABLE", False):
            ear = ears.Ear()
        self.assertEqual(ear.transcribe(b"\x00\x00"), "")


if __name__ == "__main__":
    unittest.main()
