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
                self.model.to(self.device)
                print("✅ Moonshine Loaded Successfully!")
            except Exception as e:
                import traceback
                print(f"❌ Moonshine Load Error: {e}")
                traceback.print_exc()

    def transcribe(self, raw_pcm: bytes) -> str:
        if not self.model or not self.processor: 
            print("❌ Ear: Model or processor not loaded.")
            return ""

        print(f"👂 Ear.transcribe: received raw_pcm of length {len(raw_pcm)} bytes")
        # 1. Convert bytes to float32
        audio_float = pcm_to_float(raw_pcm)

        # 2. Resample 48k (Mumble) -> 16k (Moonshine)
        audio_16k = resample_audio(audio_float, 48000, 16000)
        print(f"👂 Ear.transcribe: resampled 16k audio length: {len(audio_16k)} samples ({len(audio_16k)/16000:.2f}s)")

        # 3. Transcribe using transformers
        try:
            inputs = self.processor(audio_16k, sampling_rate=16000, return_tensors="pt")
            print(f"👂 Ear.transcribe: processor output keys: {list(inputs.keys())}")
            for k, v in inputs.items():
                if hasattr(v, 'shape'):
                    print(f"   Key: {k}, Shape: {list(v.shape)}, Dtype: {v.dtype}")
            
            # Move to device and cast float values to model's parameter dtype (e.g. float16 on cuda)
            processed_inputs = {}
            for k, v in inputs.items():
                if torch.is_floating_point(v):
                    processed_inputs[k] = v.to(device=self.device, dtype=self.model.dtype)
                else:
                    processed_inputs[k] = v.to(self.device)
            
            with torch.no_grad():
                generated_ids = self.model.generate(**processed_inputs)
            print(f"👂 Ear.transcribe: generated token IDs length: {len(generated_ids[0]) if len(generated_ids) > 0 else 0}")
            
            transcription = self.processor.batch_decode(generated_ids, skip_special_tokens=True)
            print(f"👂 Ear.transcribe: decoded text: '{transcription[0]}'")
            return transcription[0].strip()
        except Exception as e:
            import traceback
            print(f"❌ Transcription Error: {e}")
            traceback.print_exc()
            return ""


