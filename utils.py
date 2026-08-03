from functools import lru_cache
import logging
import sys
import numpy as np
import ssl

def setup_logger(name="MumbleButler", level=logging.INFO):
    """Sets up a standardized logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger

def patch_ssl():
    """Fixes SSL context for legacy/unverified connections."""
    if not hasattr(ssl, 'wrap_socket'):
        def wrap_socket(sock, **kwargs):
            context = ssl.SSLContext(kwargs.get('ssl_version', ssl.PROTOCOL_TLS_CLIENT))
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context.wrap_socket(sock, server_hostname=kwargs.get('server_hostname'))
        ssl.wrap_socket = wrap_socket

@lru_cache(maxsize=128)
def get_resample_indices(input_len: int, input_rate: int, target_rate: int):
    """Retrieves index arrays for resampling, cached via LRU cache."""
    source_indices = np.arange(input_len)
    target_len = int(input_len * (target_rate / input_rate))
    target_indices = np.linspace(0, input_len - 1, target_len)
    return (source_indices, target_indices)

def resample_int16(audio_data: np.ndarray, input_rate: int, target_rate: int) -> np.ndarray:
    """Resamples int16 audio directly using linear interpolation, utilizing cached indices."""
    if input_rate == target_rate:
        return audio_data

    source_indices, target_indices = get_resample_indices(len(audio_data), input_rate, target_rate)
    return np.interp(target_indices, source_indices, audio_data).astype(np.int16)

