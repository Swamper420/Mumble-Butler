import time
import threading
import numpy as np
import config

class UserVoiceStream:
    def __init__(self, name, bot=None):
        self.name = name
        self.buffer = bytearray()
        self.last_packet_time = time.time()
        self.is_processing = False
        self.lock = threading.Lock()
        
        # Streaming wakeword state
        self.wakeword_detected = False
        self.accumulated_16k_int16 = np.array([], dtype=np.int16)
        self.wakeword_model = None
        self.pending_wakeword_chunks = 0
        
        if bot and hasattr(bot, 'wakeword_detector') and bot.wakeword_detector.enabled:
            try:
                self.wakeword_model = bot.wakeword_detector.create_model_instance()
            except Exception as e:
                print(f"❌ Error instantiating openwakeword for {name}: {e}")

    def add_data(self, pcm_data):
        with self.lock:
            self.buffer.extend(pcm_data)
            max_seconds = getattr(config, 'MAX_AUDIO_BUFFER_SECONDS', 10.0)
            max_bytes = int(48000 * 2 * max_seconds)
            if len(self.buffer) > max_bytes:
                self.buffer = self.buffer[-max_bytes:]
            self.last_packet_time = time.time()

    def extract_audio(self):
        with self.lock:
            data = bytes(self.buffer)
            self.buffer.clear()
            self.wakeword_detected = False
            self.accumulated_16k_int16 = np.array([], dtype=np.int16)
            self.pending_wakeword_chunks = 0
            if self.wakeword_model:
                try:
                    self.wakeword_model.reset()
                except:
                    pass
            return data

