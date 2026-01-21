import threading
import time
from modules.audio_buffer import UserVoiceStream
import config

class AudioManager:
    def __init__(self):
        self.user_streams = {}
        self.lock = threading.Lock()

    def add_audio(self, user_name, pcm_data):
        """Thread-safe method to add audio data to a user's stream."""
        with self.lock:
            if user_name not in self.user_streams:
                self.user_streams[user_name] = UserVoiceStream(user_name)
            self.user_streams[user_name].add_data(pcm_data)

    def prune_streams(self):
        """Optional: Remove old/empty streams to save memory."""
        with self.lock:
            # Simple cleanup logic could go here if needed
            pass

    def get_processable_audio(self):
        """
        Scans all streams. Yields (user_name, raw_audio) for any stream
        that has finished speaking (silence detected).
        """
        now = time.time()

        # Snapshot keys to avoid locking during iteration if possible,
        # or lock briefly to get the list.
        with self.lock:
            active_users = list(self.user_streams.keys())

        for name in active_users:
            if name in config.IGNORED_USERS:
                continue

            stream = self.user_streams[name]

            # Check stream state
            with stream.lock:
                is_silence = (now - stream.last_packet_time) > config.SILENCE_THRESHOLD
                has_data = len(stream.buffer) > 0
                is_processing = stream.is_processing

            if is_silence and has_data and not is_processing:
                raw_audio = stream.extract_audio()

                # Only yield if it meets length requirements
                if len(raw_audio) >= (48000 * 2 * config.MIN_AUDIO_LENGTH):
                    stream.is_processing = True
                    yield name, raw_audio, stream
