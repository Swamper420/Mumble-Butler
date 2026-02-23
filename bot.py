import os
import subprocess
import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pymumble_py3 as pymumble
import config

# Utilities
from utils import patch_ssl

# Modules
from modules.brain import Brain
from modules.ears import Ear
from modules.voice import Voice
from modules.audio_manager import AudioManager

# Logic Handlers
from handlers.text import TextHandler
from handlers.voice import VoiceHandler

class MadnessBot:
    def __init__(self):
        # Apply SSL patch for legacy/unverified connections
        patch_ssl()

        # Initialize basic audio resources
        self._load_chime()

        # Core Modules
        self.brain = Brain()
        self.ear = Ear()
        self.voice = Voice()
        self.audio_manager = AudioManager()
        # music playback engine replaces external botamusique
        from modules.music_player import MusicPlayer
        self.music = MusicPlayer(self)

        # Logic Handlers
        self.text_handler = TextHandler(self)
        self.voice_handler = VoiceHandler(self)

        # State
        self.listening_enabled = True
        self.mumble = None
        self.my_channel_id = None

        # Concurrency
        self.loop = asyncio.new_event_loop()
        self.queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _load_chime(self):
        """Loads the chime sound effect into memory."""
        self.chime_pcm = None
        if os.path.exists(config.CHIME_FILE):
            try:
                subprocess.run([
                    'ffmpeg', '-y', '-i', config.CHIME_FILE,
                    '-f', 's16le', '-acodec', 'pcm_s16le',
                    '-ar', '48000', '-ac', '1', 'chime.raw'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                with open('chime.raw', 'rb') as f:
                    self.chime_pcm = f.read()

                if os.path.exists('chime.raw'):
                    os.remove('chime.raw')
                print(f"🔔 Chime loaded ({len(self.chime_pcm)} bytes)")
            except Exception as e:
                print(f"⚠️ Chime load error: {e}")

    def setup_mumble(self):
        """Initializes Mumble connection and callbacks."""
        print(f"🔌 Connecting to {config.SERVER_IP}...")
        self.mumble = pymumble.Mumble(
            config.SERVER_IP,
            config.BOT_USERNAME,
            password=config.PASSWORD,
            port=config.SERVER_PORT
        )

        # Callbacks
        self.mumble.callbacks.set_callback("user_updated", self.on_user_updated)
        self.mumble.callbacks.set_callback("text_received", self.text_handler.handle)

        self.mumble.set_receive_sound(True)
        self.mumble.callbacks.set_callback("sound_received", self.on_sound_received)

    def run(self):
        """Main application loop."""
        print("🚀 Starting Bot...")
        threading.Thread(target=self._start_async_loop, daemon=True).start()

        # Connection / Reconnection Loop
        while True:
            try:
                self.setup_mumble()
                self.mumble.start()
                self.mumble.is_ready()

                channel = self.mumble.channels.find_by_name(config.TARGET_CHANNEL)
                if channel:
                    channel.move_in()

                print("✅ Connected!")

                # Keep main thread alive while monitoring connection
                while self.mumble.is_alive():
                    if self.mumble.users.myself:
                        self.my_channel_id = self.mumble.users.myself['channel_id']
                    time.sleep(1)

                print("⚠️ Disconnected from server.")

            except KeyboardInterrupt:
                self.shutdown()
                break
            except Exception as e:
                print(f"⚠️ Connection error: {e}")
            finally:
                if self.mumble:
                    try: self.mumble.stop()
                    except: pass

            print(f"🔄 Reconnecting in {config.RECONNECT_DELAY} seconds...")
            time.sleep(config.RECONNECT_DELAY)

            # Clear audio buffers on reconnect to prevent stale processing
            self.audio_manager.user_streams.clear()

    def shutdown(self):
        print("\nShutting down...")
        self.save_stats()
        if self.mumble:
            self.mumble.stop()

    def _start_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(asyncio.gather(
            self.tts_worker(),
            self.audio_processing_worker()
        ))

    # --- WORKERS ---

    async def tts_worker(self):
        """Consumes text from queue and generates speech."""
        while True:
            text = await self.queue.get()
            if self.mumble and self.mumble.sound_output:
                # Generate PCM in thread pool to avoid blocking async loop
                pcm_data = await self.loop.run_in_executor(
                    self.executor,
                    self.voice.generate_pcm,
                    text
                )
                if pcm_data:
                    try: self.mumble.sound_output.add_sound(pcm_data)
                    except: pass
            self.queue.task_done()

    async def audio_processing_worker(self):
        """Polls AudioManager for complete voice clips to process."""
        while True:
            await asyncio.sleep(config.POLL_RATE)
            if not self.listening_enabled: continue

            # Get user audio streams that have finished recording (silence detected)
            for user, raw_audio, stream in self.audio_manager.get_processable_audio():

                # Double check ignore list
                if user in config.IGNORED_USERS:
                    stream.is_processing = False
                    continue

                # Offload transcription and logic to thread pool
                self.loop.run_in_executor(
                    self.executor,
                    self.process_voice_command,
                    user, raw_audio, stream
                )

    def process_voice_command(self, user, raw_audio, stream):
        """Transcribes audio and routes to VoiceHandler."""
        try:
            text = self.ear.transcribe(raw_audio)
            if text:
                print(f"[{user}]: {text}")
                self.voice_handler.handle(user, text)
        except Exception as e:
            print(f"Error processing voice command: {e}")
        finally:
            # Important: Unlock the stream for new input
            stream.is_processing = False

    # --- PUBLIC HELPERS (Used by Handlers) ---

    def say_async(self, text):
        """Queues a message to be spoken by TTS."""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, text)

    # legacy compatibility helpers ------------------------------------------------
    def send_chat(self, text):
        """Sends a text message to the current Mumble channel."""
        if self.mumble and self.my_channel_id is not None:
            try: self.mumble.channels[self.my_channel_id].send_text_message(text)
            except: pass

    # The following are thin wrappers that voice/text handlers can call
    # when they previously produced botamusique chat commands.  They simply
    # forward to the internal music player.
    def play(self, query: str):
        return self.music.queue_track(query)

    def skip(self):
        return self.music.skip()

    def stop_music(self):
        return self.music.stop()

    def set_volume(self, level: int):
        return self.music.set_volume(level)

    def pause_music(self):
        return self.music.pause()

    def resume_music(self):
        return self.music.resume()

    def repeat_music(self, count: int):
        return self.music.repeat(count)

    def set_mode(self, mode: str):
        return self.music.set_mode(mode)

    # --- CALLBACKS ---

    def on_sound_received(self, user, sound_chunk):
        """Mumble callback for incoming audio packets."""
        if not self.listening_enabled or not user: return
        if user['name'] in config.IGNORED_USERS: return

        self.audio_manager.add_audio(user['name'], sound_chunk.pcm)

    def on_user_updated(self, user, mods):
        """Mumble callback for user state changes (join/move)."""
        if "channel_id" not in mods: return
        name = user['name']

        if name == config.BOT_USERNAME or name in config.IGNORED_USERS: return

        new_ch = mods['channel_id']
        if new_ch == self.my_channel_id:
             self.say_async(f"Welcome {name}")

    def load_stats(self):
        # Placeholder for persistence logic
        pass

    def save_stats(self):
        # Placeholder for persistence logic
        pass
