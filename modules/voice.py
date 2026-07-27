import os
import torch
import numpy as np
import re
import urllib.request
import config
from utils import resample_audio, float_to_pcm

class Voice:
    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model_type = getattr(config, "CHATTERBOX_MODEL", "nano").lower()
        self.engine = f"chatterbox-{model_type}"
        self.conds_cache = {}
        self.models = {}

        # Optimize PyTorch CPU threading & CUDA matrix flags to relieve CPU bottlenecks
        cpu_cores = os.cpu_count() or 4
        if hasattr(torch, "set_num_threads"):
            torch.set_num_threads(min(cpu_cores, 8))
        if hasattr(torch, "set_num_interop_threads"):
            torch.set_num_interop_threads(min(cpu_cores, 4))
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

        self.model = self._load_model_instance(model_type)
        self.models[model_type] = self.model
        self.current_voice_id = getattr(config, "CHATTERBOX_DEFAULT_VOICE", "michael")
        self._ensure_default_voice()

        # Pre-warm default voice
        voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
        default_path = os.path.join(voice_dir, f"{self.current_voice_id}.wav")
        if os.path.exists(default_path):
            try:
                print(f"🔥 Pre-warming conditionals cache for default voice: {self.current_voice_id}...")
                with torch.inference_mode():
                    self.model.prepare_conditionals(default_path)
                self.conds_cache[self.current_voice_id] = self.model.conds
            except Exception as e:
                print(f"⚠️ Failed to pre-warm default voice cache: {e}")

    def _load_model_instance(self, model_type_str: str):
        model_type = (model_type_str or "nano").lower()
        print(f"🗣️ Loading Chatterbox ({model_type.upper()}) TTS ({self.device})...")
        if "finnish" in model_type:
            try:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
            except Exception:
                from chatterbox.tts import ChatterboxTTS
                model = ChatterboxTTS.from_pretrained(device=self.device)

            repo_id = "Finnish-NLP/Chatterbox-Finnish"
            filename = "models/best_finnish_multilingual_cp986.safetensors"
            print(f"📥 Loading finetuned weights from HuggingFace ({repo_id})...")
            try:
                from safetensors.torch import load_file
                from huggingface_hub import hf_hub_download

                local_weights = os.path.join("models", "best_finnish_multilingual_cp986.safetensors")
                if os.path.exists(local_weights):
                    weights_path = local_weights
                else:
                    weights_path = hf_hub_download(repo_id=repo_id, filename=filename)

                checkpoint_state = load_file(weights_path)
                t3_state_dict = {k[3:] if k.startswith("t3.") else k: v for k, v in checkpoint_state.items()}
                if hasattr(model, "t3"):
                    # Resize text_emb and text_head if vocab size mismatched
                    if "text_emb.weight" in t3_state_dict and hasattr(model.t3, "text_emb"):
                        ckpt_vocab_size, ckpt_emb_dim = t3_state_dict["text_emb.weight"].shape
                        if model.t3.text_emb.weight.shape[0] != ckpt_vocab_size:
                            print(f"🔄 Resizing T3 text_emb from {model.t3.text_emb.weight.shape[0]} to {ckpt_vocab_size}...")
                            model.t3.text_emb = torch.nn.Embedding(ckpt_vocab_size, ckpt_emb_dim).to(self.device)

                    if "text_head.weight" in t3_state_dict and hasattr(model.t3, "text_head"):
                        ckpt_vocab_size, ckpt_in_dim = t3_state_dict["text_head.weight"].shape
                        if model.t3.text_head.weight.shape[0] != ckpt_vocab_size:
                            print(f"🔄 Resizing T3 text_head from {model.t3.text_head.weight.shape[0]} to {ckpt_vocab_size}...")
                            has_bias = getattr(model.t3.text_head, "bias", None) is not None
                            model.t3.text_head = torch.nn.Linear(ckpt_in_dim, ckpt_vocab_size, bias=has_bias).to(self.device)

                    model.t3.load_state_dict(t3_state_dict, strict=False)
                    print("✅ Finnish Chatterbox finetuned weights injected successfully.")
                else:
                    print("⚠️ Base model does not have t3 attribute. Could not inject finetuned weights.")
            except Exception as e:
                print(f"⚠️ Failed to load Finnish-NLP Chatterbox finetuned weights: {e}")
            return model
        elif model_type in ["standard", "base", "chatterbox"]:
            from chatterbox.tts import ChatterboxTTS
            return ChatterboxTTS.from_pretrained(device=self.device)
        elif model_type in ["multilingual", "mtl"]:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            return ChatterboxMultilingualTTS.from_pretrained(device=self.device)
        elif model_type == "nano":
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            try:
                return ChatterboxTurboTTS.from_pretrained(device=self.device, nano=True)
            except TypeError:
                print("⚠️ Installed chatterbox-tts does not accept nano=True. Falling back to standard ChatterboxTurboTTS.")
                return ChatterboxTurboTTS.from_pretrained(device=self.device)
        else:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            return ChatterboxTurboTTS.from_pretrained(device=self.device)

    def clear_voice_cache(self, keep_voice: str = None):
        """Clears cached voice conditionals from dictionary and frees GPU VRAM."""
        if keep_voice:
            keys_to_del = [k for k in self.conds_cache if k != keep_voice]
            for k in keys_to_del:
                del self.conds_cache[k]
        else:
            self.conds_cache.clear()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _ensure_default_voice(self):
        """Creates the voice directory and downloads a default speech WAV if missing."""
        voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
        os.makedirs(voice_dir, exist_ok=True)
        default_path = os.path.join(voice_dir, f"{self.current_voice_id}.wav")
        if not os.path.exists(default_path):
            print(f"📥 Downloading default voice reference to {default_path}...")
            url = "https://github.com/voxserv/audio_quality_testing_samples/raw/refs/heads/master/testaudio/16000/test01_20s.wav"
            try:
                urllib.request.urlretrieve(url, default_path)
                print("✅ Default voice reference downloaded successfully.")
            except Exception as e:
                print(f"⚠️ Failed to download default voice: {e}")

    def sanitize_tts_text(self, text: str) -> str:
        """Sanitizes and normalizes input text for Chatterbox TTS generation to prevent out-of-range special token errors."""
        if not text:
            return ""
        # 1. Strip surrounding whitespace
        cleaned = str(text).strip()
        if not cleaned:
            return ""

        # 2. Remove control characters and non-printable unicode characters
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)

        # 3. Check if speakable text exists (excluding bracketed tags like [sigh] or <tag>)
        speakable = re.sub(r'\[.*?\]', '', cleaned)
        speakable = re.sub(r'<.*?>', '', speakable).strip()

        if not speakable:
            return ""

        # 4. Handle extremely short text prompts (e.g. 1-2 chars without punctuation)
        # Chatterbox flow models can trigger out-of-range special token errors on very short unpunctuated inputs.
        if len(speakable) <= 3 and not cleaned.endswith(('.', '!', '?', ':', ';', ',')):
            cleaned = cleaned + "."

        return cleaned

    def generate_pcm(self, text: str, voice_id: str = None, model_type: str = None):
        """Generates 48khz PCM bytes from text using Chatterbox."""
        cleaned_text = self.sanitize_tts_text(text)
        if not cleaned_text:
            print("⚠️ TTS Warning: Input text is empty or contains no speakable content after sanitization.")
            return None

        try:
            target_voice = voice_id or self.current_voice_id
            voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
            voice_path = os.path.join(voice_dir, f"{target_voice}.wav")

            # Check if voice_path exists, fallback if not
            if not os.path.exists(voice_path):
                default_voice = getattr(config, "CHATTERBOX_DEFAULT_VOICE", "michael")
                voice_path = os.path.join(voice_dir, f"{default_voice}.wav")
                if not os.path.exists(voice_path):
                    self._ensure_default_voice()
                target_voice = default_voice

            if not os.path.exists(voice_path):
                raise FileNotFoundError(f"Reference voice wav not found at {voice_path}")

            target_model_key = (model_type or getattr(config, "CHATTERBOX_MODEL", "nano")).lower()
            if target_model_key not in self.models:
                self.models[target_model_key] = self._load_model_instance(target_model_key)
            active_model = self.models[target_model_key]

            with torch.inference_mode():
                cache_key = f"{target_model_key}:{target_voice}"
                if cache_key in self.conds_cache:
                    active_model.conds = self.conds_cache[cache_key]
                elif target_voice in self.conds_cache and target_model_key == getattr(config, "CHATTERBOX_MODEL", "nano").lower():
                    active_model.conds = self.conds_cache[target_voice]
                else:
                    # Evict previous voice conditionals if cache limit reached
                    max_cache = getattr(config, "CHATTERBOX_VOICE_CACHE_LIMIT", 1)
                    if max_cache > 0:
                        while len(self.conds_cache) >= max_cache:
                            oldest_voice = next(iter(self.conds_cache))
                            del self.conds_cache[oldest_voice]
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()

                    active_model.prepare_conditionals(voice_path)
                    self.conds_cache[cache_key] = active_model.conds

                # Generate audio using active_model with cached conditionals
                gen_kwargs = {
                    "text": cleaned_text,
                    "audio_prompt_path": None,
                    "temperature": getattr(config, "CHATTERBOX_TEMPERATURE", 0.8),
                }
                if "multilingual" in type(active_model).__name__.lower() or hasattr(active_model, "languages") or "finnish" in target_model_key:
                    gen_kwargs["language_id"] = getattr(config, "CHATTERBOX_LANGUAGE", "fi")

                if "finnish" in target_model_key:
                    gen_kwargs["repetition_penalty"] = getattr(config, "CHATTERBOX_REPETITION_PENALTY", 1.2)
                    gen_kwargs["exaggeration"] = getattr(config, "CHATTERBOX_EXAGGERATION", 0.6)

                try:
                    wav_tensor = active_model.generate(**gen_kwargs)
                except TypeError as err:
                    if "language_id" in str(err):
                        wav_tensor = active_model.generate(
                            cleaned_text,
                            language_id=getattr(config, "CHATTERBOX_LANGUAGE", "fi"),
                            audio_prompt_path=None,
                            temperature=getattr(config, "CHATTERBOX_TEMPERATURE", 0.8),
                        )
                    else:
                        wav_tensor = active_model.generate(
                            cleaned_text,
                            audio_prompt_path=None,
                            temperature=getattr(config, "CHATTERBOX_TEMPERATURE", 0.8),
                        )

                # Resample and convert float32 to PCM int16 directly on GPU tensor if available
                sr = getattr(self.model, "sr", 24000)
                if torch.is_tensor(wav_tensor) and wav_tensor.numel() > 0:
                    curr = wav_tensor.detach()
                    if sr != 48000:
                        if curr.ndim == 1:
                            curr = curr.unsqueeze(0).unsqueeze(0)
                        elif curr.ndim == 2:
                            curr = curr.unsqueeze(1)
                        target_len = int(curr.shape[-1] * (48000 / sr))
                        curr = torch.nn.functional.interpolate(
                            curr, size=target_len, mode='linear', align_corners=False
                        ).squeeze()
                    else:
                        curr = curr.squeeze()

                    pcm_tensor = (curr * 32767).clamp(-32768, 32767).to(torch.int16)
                    return pcm_tensor.cpu().numpy().tobytes()

                # Fallback for non-tensor outputs
                audio_np = wav_tensor.detach().cpu().numpy() if torch.is_tensor(wav_tensor) else wav_tensor
                if audio_np.ndim > 1:
                    audio_np = audio_np.squeeze()

                audio_48k = resample_audio(audio_np, sr, 48000)
                return float_to_pcm(audio_48k)
        except Exception as e:
            err_msg = str(e)
            print(f"TTS Error: {err_msg}")

            # Autorecovery logic for CUDA device-side assertions / out-of-range token errors
            is_cuda_assert = any(kw in err_msg.lower() for kw in [
                "cuda error", "device-side assert", "out-of-range special tokens", "indexselect", "indexing"
            ])

            if is_cuda_assert:
                print("🔄 Triggering TTS Autorecovery mechanism due to CUDA/Token assertion failure...")
                try:
                    # 1. Evict cached voice conditionals and model instances
                    self.clear_voice_cache()
                    target_model_key = (model_type or getattr(config, "CHATTERBOX_MODEL", "nano")).lower()
                    if target_model_key in self.models:
                        del self.models[target_model_key]

                    # 2. Attempt CUDA cache cleanup
                    if torch.cuda.is_available():
                        try:
                            torch.cuda.empty_cache()
                            if hasattr(torch.cuda, "ipc_collect"):
                                torch.cuda.ipc_collect()
                        except Exception:
                            pass

                    # 3. Reload model instance (try GPU first, fallback to CPU if CUDA context is corrupted)
                    print(f"🔄 Reloading model '{target_model_key}' for recovery...")
                    try:
                        recovered_model = self._load_model_instance(target_model_key)
                    except Exception as reload_err:
                        print(f"⚠️ Failed GPU reload ({reload_err}), falling back to CPU device...")
                        self.device = "cpu"
                        recovered_model = self._load_model_instance(target_model_key)

                    self.models[target_model_key] = recovered_model

                    # 4. Prepare conditionals and retry generation once
                    print("🔄 Retrying TTS generation with recovered model...")
                    recovered_model.prepare_conditionals(voice_path)

                    retry_gen_kwargs = {
                        "text": cleaned_text,
                        "audio_prompt_path": None,
                        "temperature": getattr(config, "CHATTERBOX_TEMPERATURE", 0.8),
                    }
                    if "multilingual" in type(recovered_model).__name__.lower() or hasattr(recovered_model, "languages") or "finnish" in target_model_key:
                        retry_gen_kwargs["language_id"] = getattr(config, "CHATTERBOX_LANGUAGE", "fi")

                    if "finnish" in target_model_key:
                        retry_gen_kwargs["repetition_penalty"] = getattr(config, "CHATTERBOX_REPETITION_PENALTY", 1.2)
                        retry_gen_kwargs["exaggeration"] = getattr(config, "CHATTERBOX_EXAGGERATION", 0.6)

                    with torch.inference_mode():
                        wav_tensor = recovered_model.generate(**retry_gen_kwargs)

                    sr = getattr(self.model, "sr", 24000)
                    if torch.is_tensor(wav_tensor) and wav_tensor.numel() > 0:
                        curr = wav_tensor.detach()
                        if sr != 48000:
                            if curr.ndim == 1:
                                curr = curr.unsqueeze(0).unsqueeze(0)
                            elif curr.ndim == 2:
                                curr = curr.unsqueeze(1)
                            target_len = int(curr.shape[-1] * (48000 / sr))
                            curr = torch.nn.functional.interpolate(
                                curr, size=target_len, mode='linear', align_corners=False
                            ).squeeze()
                        else:
                            curr = curr.squeeze()

                        pcm_tensor = (curr * 32767).clamp(-32768, 32767).to(torch.int16)
                        print("✅ TTS Autorecovery successfully generated PCM audio!")
                        return pcm_tensor.cpu().numpy().tobytes()
                except Exception as rec_err:
                    print(f"❌ TTS Autorecovery retry failed: {rec_err}")

            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            return None
