import numpy as np
import ssl

def patch_ssl():
    """Fixes SSL context for legacy/unverified connections."""
    if not hasattr(ssl, 'wrap_socket'):
        def wrap_socket(sock, **kwargs):
            context = ssl.SSLContext(kwargs.get('ssl_version', ssl.PROTOCOL_TLS_CLIENT))
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context.wrap_socket(sock, server_hostname=kwargs.get('server_hostname'))
        ssl.wrap_socket = wrap_socket

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


def adjust_volume_pcm(raw_bytes: bytes, factor: float) -> bytes:
    """Apply a simple volume multiplier to 16‑bit PCM data.

    Works in-place by converting to numpy, scaling, clipping and returning
    the modified bytes.  Factor should be between 0.0 (silence) and
    ~2.0 (double volume).
    """
    audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
    audio *= factor
    audio = np.clip(audio, -32768, 32767).astype(np.int16)
    return audio.tobytes()
