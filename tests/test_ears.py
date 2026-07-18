import sys
import unittest
from unittest.mock import MagicMock, patch

from modules import ears

class EarTranscribeTests(unittest.TestCase):
    @patch("modules.ears.resample_audio", return_value=[0.1])
    @patch("modules.ears.pcm_to_float", return_value=[0.1])
    @patch("modules.ears.torch")
    def test_transcribe_calls_moonshine_model(self, mock_torch, _pcm_to_float, _resample_audio):
        fake_processor = MagicMock()
        fake_processor.return_value = {"input_values": MagicMock()}
        fake_processor.batch_decode.return_value = ["hello moonshine"]
        
        fake_model = MagicMock()
        fake_model.generate.return_value = [1, 2, 3]

        with patch.object(ears, "STT_AVAILABLE", True), \
             patch.object(ears, "AutoProcessor") as mock_processor_cls, \
             patch.object(ears, "MoonshineStreamingForConditionalGeneration") as mock_model_cls:
            
            mock_processor_cls.from_pretrained.return_value = fake_processor
            mock_model_cls.from_pretrained.return_value = fake_model
            
            ear = ears.Ear()
            text = ear.transcribe(b"\x00\x00")

        self.assertEqual(text, "hello moonshine")
        mock_processor_cls.from_pretrained.assert_called_once_with(ears.config.MOONSHINE_MODEL_SIZE)
        mock_model_cls.from_pretrained.assert_called_once_with(ears.config.MOONSHINE_MODEL_SIZE)
        fake_model.to.assert_called_once_with(ears.config.MOONSHINE_DEVICE)
        fake_processor.assert_called_once()
        fake_model.generate.assert_called_once()
        fake_processor.batch_decode.assert_called_once_with([1, 2, 3], skip_special_tokens=True)

    def test_transcribe_returns_empty_string_when_model_unavailable(self):
        with patch.object(ears, "STT_AVAILABLE", False):
            ear = ears.Ear()
        self.assertEqual(ear.transcribe(b"\x00\x00"), "")

if __name__ == "__main__":
    unittest.main()
