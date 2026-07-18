import threading
import time
import numpy as np
from modules.audio_buffer import UserVoiceStream
import config

class AudioManager:
    def __init__(self, bot=None):
        self.bot = bot
        self.user_streams = {}
        self.lock = threading.Lock()

    def add_audio(self, user_name, pcm_data):
        """Thread-safe method to add audio data to a user's stream."""
        with self.lock:
            if user_name not in self.user_streams:
                self.user_streams[user_name] = UserVoiceStream(user_name, self.bot)
            stream = self.user_streams[user_name]
            stream.add_data(pcm_data)

        # Run openwakeword on-the-fly incrementally
        if self.bot and hasattr(self.bot, 'wakeword_detector') and self.bot.wakeword_detector.enabled and stream.wakeword_model:
            with stream.lock:
                if not stream.wakeword_detected:
                    from utils import pcm_to_float, resample_audio
                    
                    # Downsample incoming 48kHz audio to 16kHz
                    audio_float = pcm_to_float(pcm_data)
                    audio_16k_float = resample_audio(audio_float, 48000, 16000)
                    audio_16k_int16 = (audio_16k_float * 32767.0).clip(-32768, 32767).astype(np.int16)
                    
                    # Accumulate and predict in 1280-sample (80ms) chunks
                    stream.accumulated_16k_int16 = np.concatenate((stream.accumulated_16k_int16, audio_16k_int16))
                    
                    chunk_size = 1280
                    while len(stream.accumulated_16k_int16) >= chunk_size:
                        chunk = stream.accumulated_16k_int16[:chunk_size]
                        stream.accumulated_16k_int16 = stream.accumulated_16k_int16[chunk_size:]
                        
                        predictions = stream.wakeword_model.predict(chunk)
                        detected = False
                        for score in predictions.values():
                            if score >= config.WAKEWORD_THRESHOLD:
                                detected = True
                                break
                        
                        if detected:
                            stream.wakeword_detected = True
                            self.bot.logger.info(f"🎙️ Wake word detected in stream for {user_name}!")
                            
                            # Play chime instantly and interrupt active speech
                            self.bot.stop_speaking()
                            
                            if self.bot.chime_pcm and self.bot.mumble and self.bot.mumble.sound_output:
                                try:
                                    self.bot.mumble.sound_output.add_sound(self.bot.chime_pcm)
                                except Exception as e:
                                    self.bot.logger.error(f"Error playing chime: {e}")
                            break

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
                
                # If wakeword is disabled/bypassed, treat as always detected
                wakeword_ok = True
                if self.bot and hasattr(self.bot, 'wakeword_detector') and self.bot.wakeword_detector.enabled:
                    wakeword_ok = stream.wakeword_detected

            if is_silence and has_data and not is_processing:
                # If wakeword is required but not detected, discard the stream's audio
                if not wakeword_ok:
                    with stream.lock:
                        stream.buffer.clear()
                        stream.accumulated_16k_int16 = np.array([], dtype=np.int16)
                    continue

                raw_audio = stream.extract_audio()

                # Only yield if it meets length requirements
                if len(raw_audio) >= (48000 * 2 * config.MIN_AUDIO_LENGTH):
                    stream.is_processing = True
                    yield name, raw_audio, stream
