import torch
import numpy as np
import config
from utils import resample_audio, pcm_to_float

try:
    from transformers import AutoProcessor, MoonshineStreamingForConditionalGeneration
    STT_AVAILABLE = True
except ImportError as e:
    STT_AVAILABLE = False
    import traceback
    print(f"❌ Ear: ImportError loading transformers: {e}")
    traceback.print_exc()

class Ear:
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = config.MOONSHINE_DEVICE
        if STT_AVAILABLE:
            try:
                print(f"👂 Loading Moonshine ({self.device})...")
                self.processor = AutoProcessor.from_pretrained(config.MOONSHINE_MODEL_SIZE)
                self.model = MoonshineStreamingForConditionalGeneration.from_pretrained(config.MOONSHINE_MODEL_SIZE)
                if self.device == 'cuda' and torch.cuda.is_available():
                    self.model = self.model.half()
                self.model.to(self.device)
                print("✅ Moonshine Loaded Successfully!")
            except Exception as e:
                import traceback
                print(f"❌ Moonshine Load Error: {e}")
                traceback.print_exc()

    def transcribe(self, raw_pcm: bytes) -> str:
        if not self.model or not self.processor: return ""

        # 1. Convert bytes to float32
        audio_float = pcm_to_float(raw_pcm)
        if len(audio_float) == 0:
            return ""

        # 2. Trim leading and trailing silence (< 0.001 amplitude)
        non_silent = np.where(np.abs(audio_float) > 0.001)[0]
        if len(non_silent) > 0:
            audio_float = audio_float[non_silent[0]:non_silent[-1] + 1]
        else:
            return ""

        # 3. Resample 48k (Mumble) -> 16k (Moonshine)
        audio_16k = resample_audio(audio_float, 48000, 16000)

        # 4. Transcribe using transformers
        try:
            inputs = self.processor(audio_16k, sampling_rate=16000, return_tensors="pt")
            
            # Move to device and cast float values to model's parameter dtype (e.g. float16 on cuda)
            processed_inputs = {}
            for k, v in inputs.items():
                if torch.is_floating_point(v):
                    processed_inputs[k] = v.to(device=self.device, dtype=self.model.dtype)
                else:
                    processed_inputs[k] = v.to(self.device)
            
            with torch.no_grad():
                generated_ids = self.model.generate(**processed_inputs)
            transcription = self.processor.batch_decode(generated_ids, skip_special_tokens=True)
            return transcription[0].strip()
        except Exception as e:
            print(f"❌ Transcription Error: {e}")
            return ""



