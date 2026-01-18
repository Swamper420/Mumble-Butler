import numpy as np

def pcm_to_float(raw_bytes: bytes) -> np.ndarray:
    """Converts raw PCM bytes to normalized float32 (-1.0 to 1.0)."""
    audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)
    # Handle stereo to mono if needed
    if len(audio_int16) % 2 != 0:
        audio_int16 = audio_int16[:-1]

    # Simple check: if we assume stereo input (standard Mumble), average channels
    # Note: pymumble usually gives mono, but if you encounter stereo issues:
    # audio_stereo = audio_int16.reshape(-1, 2)
    # audio_mono = audio_stereo.mean(axis=1)

    return (audio_int16 / 32768.0).astype(np.float32)

def resample_audio(audio_data: np.ndarray, input_rate: int, target_rate: int) -> np.ndarray:
    """Resamples audio using linear interpolation (numpy only)."""
    if input_rate == target_rate:
        return audio_data

    source_indices = np.arange(len(audio_data))
    target_len = int(len(audio_data) * (target_rate / input_rate))
    target_indices = np.linspace(0, len(audio_data) - 1, target_len)

    return np.interp(target_indices, source_indices, audio_data)

def float_to_pcm(audio_float: np.ndarray) -> bytes:
    """Converts float32 audio back to int16 bytes."""
    return (audio_float * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
