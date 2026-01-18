import time
import threading

class UserVoiceStream:
    def __init__(self, name):
        self.name = name
        self.buffer = bytearray()
        self.last_packet_time = time.time()
        self.is_processing = False
        self.lock = threading.Lock()

    def add_data(self, pcm_data):
        with self.lock:
            self.buffer.extend(pcm_data)
            self.last_packet_time = time.time()

    def extract_audio(self):
        with self.lock:
            data = bytes(self.buffer)
            self.buffer.clear()
            return data
