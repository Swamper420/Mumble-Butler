import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import torch

import config

class TestFinnishTTS(unittest.TestCase):
    def test_config_finnish_defaults(self):
        self.assertEqual(config.CHATTERBOX_MODEL, "nano")
        self.assertEqual(config.CHATTERBOX_API_MODEL, "https://huggingface.co/Finnish-NLP/Chatterbox-Finnish")
        self.assertEqual(config.CHATTERBOX_LANGUAGE, "fi")
        self.assertEqual(config.CHATTERBOX_REPETITION_PENALTY, 1.2)
        self.assertEqual(config.CHATTERBOX_EXAGGERATION, 0.6)

    @patch("torch.cuda.is_available", return_value=False)
    @patch("os.path.exists", return_value=True)
    def test_voice_multi_model_generation(self, mock_exists, mock_cuda):
        nano_model = MagicMock()
        nano_model.generate.return_value = torch.zeros(24000, dtype=torch.float32)

        finnish_model = MagicMock()
        finnish_model.__class__.__name__ = "ChatterboxMultilingualTTS"
        mock_t3 = MagicMock()
        mock_t3.text_emb.weight.shape = (704, 1024)
        mock_t3.text_head.weight.shape = (704, 1024)
        finnish_model.t3 = mock_t3
        finnish_model.generate.return_value = torch.zeros(24000, dtype=torch.float32)

        mock_turbo = MagicMock()
        mock_turbo.ChatterboxTurboTTS.from_pretrained.return_value = nano_model

        mock_mtl = MagicMock()
        mock_mtl.ChatterboxMultilingualTTS.from_pretrained.return_value = finnish_model

        mock_safetensors = MagicMock()
        mock_safetensors.load_file.return_value = {
            "t3.text_emb.weight": torch.zeros((2454, 1024)),
            "t3.text_head.weight": torch.zeros((2454, 1024))
        }

        mock_hf_hub = MagicMock()
        mock_hf_hub.hf_hub_download.return_value = "/path/to/safetensors"

        with patch.dict(sys.modules, {
            "chatterbox.tts_turbo": mock_turbo,
            "chatterbox.mtl_tts": mock_mtl,
            "safetensors.torch": mock_safetensors,
            "huggingface_hub": mock_hf_hub
        }):
            from modules.voice import Voice
            voice = Voice()
            self.assertEqual(voice.engine, "chatterbox-nano")

            # Main generation uses nano
            pcm_main = voice.generate_pcm("Hello world", voice_id="michael")
            self.assertIsNotNone(pcm_main)
            nano_model.generate.assert_called_once()

            # API generation uses Finnish model override
            pcm_api = voice.generate_pcm("Terve maailma!", voice_id="michael", model_type="https://huggingface.co/Finnish-NLP/Chatterbox-Finnish")
            self.assertIsNotNone(pcm_api)
            finnish_model.generate.assert_called_once_with(
                text="Terve maailma!",
                audio_prompt_path=None,
                temperature=0.8,
                language_id="fi",
                repetition_penalty=1.2,
                exaggeration=0.6
            )

if __name__ == "__main__":
    unittest.main()
