import threading
import time
import queue
import numpy as np
from modules.audio_buffer import UserVoiceStream
import config

class AudioManager:
    def __init__(self, bot=None):
        self.bot = bot
        self.user_streams = {}
        self.lock = threading.Lock()
        
        # Background wakeword queue and thread
        self.wakeword_queue = queue.Queue()
        self.wakeword_thread = threading.Thread(target=self._wakeword_worker, daemon=True)
        self.wakeword_thread.start()

    def add_audio(self, user_name, pcm_data):
        """Thread-safe method to add audio data to a user's stream."""
        with self.lock:
            if user_name not in self.user_streams:
                self.user_streams[user_name] = UserVoiceStream(user_name, self.bot)
            stream = self.user_streams[user_name]
            stream.add_data(pcm_data)

        # Offload wakeword checking to the background queue
        if self.bot and hasattr(self.bot, 'wakeword_detector') and self.bot.wakeword_detector.enabled and stream.wakeword_model:
            with stream.lock:
                if not stream.wakeword_detected:
                    stream.pending_wakeword_chunks += 1
                    self.wakeword_queue.put((stream, pcm_data))

    def _wakeword_worker(self):
        while True:
            try:
                item = self.wakeword_queue.get()
                if item is None:
                    break
                stream, pcm_data = item
                self._process_wakeword(stream, pcm_data)
            except Exception as e:
                if self.bot:
                    self.bot.logger.error(f"Error in wakeword worker: {e}")
            finally:
                self.wakeword_queue.task_done()

    def _process_wakeword(self, stream, pcm_data):
        with stream.lock:
            if stream.wakeword_detected:
                stream.pending_wakeword_chunks -= 1
                return

        from utils import resample_int16
        
        # Downsample incoming 48kHz audio to 16kHz directly in int16
        audio_int16 = np.frombuffer(pcm_data, dtype=np.int16)
        audio_16k_bytes = resample_int16(audio_int16, 48000, 16000).tobytes()
        
        chunks_to_predict = []
        with stream.lock:
            if stream.wakeword_detected:
                stream.pending_wakeword_chunks -= 1
                return

            # Accumulate 16k audio bytes efficiently in bytearray
            stream.accumulated_16k_bytes.extend(audio_16k_bytes)
            
            chunk_bytes = 2560  # 1280 samples * 2 bytes/sample (int16)
            while len(stream.accumulated_16k_bytes) >= chunk_bytes:
                raw_chunk = bytes(stream.accumulated_16k_bytes[:chunk_bytes])
                del stream.accumulated_16k_bytes[:chunk_bytes]
                chunks_to_predict.append(np.frombuffer(raw_chunk, dtype=np.int16))

        # Run ONNX inference outside the lock
        detected = False
        if chunks_to_predict and stream.wakeword_model:
            for chunk in chunks_to_predict:
                predictions = stream.wakeword_model.predict(chunk)
                for score in predictions.values():
                    if score >= config.WAKEWORD_THRESHOLD:
                        detected = True
                        break
                if detected:
                    break

        trigger_bot_reaction = False
        with stream.lock:
            stream.pending_wakeword_chunks -= 1
            if detected and not stream.wakeword_detected:
                stream.wakeword_detected = True
                trigger_bot_reaction = True

        if trigger_bot_reaction and self.bot:
            self.bot.logger.info(f"🎙️ Wake word detected in stream for {stream.name}!")
            
            # Play chime instantly and interrupt active speech
            self.bot.stop_speaking()
            
            self.bot.play_ack_sound()

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
                has_pending = stream.pending_wakeword_chunks > 0
                
                # If wakeword is disabled/bypassed, treat as always detected
                wakeword_ok = True
                if self.bot and hasattr(self.bot, 'wakeword_detector') and self.bot.wakeword_detector.enabled:
                    wakeword_ok = stream.wakeword_detected

            if is_silence and has_data and not is_processing and not has_pending:
                # If wakeword is required but not detected, discard the stream's audio
                if not wakeword_ok:
                    with stream.lock:
                        stream.buffer.clear()
                        stream.accumulated_16k_bytes.clear()
                    continue

                raw_audio = stream.extract_audio()

                # Only yield if it meets length requirements
                if len(raw_audio) >= (48000 * 2 * config.MIN_AUDIO_LENGTH):
                    stream.is_processing = True
                    yield name, raw_audio, stream
