import os
import subprocess
import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pymumble_py3 as pymumble
import config
from modules.audio_buffer import UserVoiceStream
from modules.brain import Brain
from modules.ears import Ear
from modules.voice import Voice

# Import new handlers
from handlers.text import TextHandler
from handlers.voice import VoiceHandler

class MadnessBot:
    def __init__(self):
        self.user_stats = {}
        self.load_stats()
        self._load_chime()

        # Core Modules
        self.brain = Brain()
        self.ear = Ear()
        self.voice = Voice()

        # Logic Handlers
        self.text_handler = TextHandler(self)
        self.voice_handler = VoiceHandler(self)

        # State
        self.listening_enabled = True
        self.user_streams = {}
        self.audio_lock = threading.Lock()

        # Mumble Connection
        self.mumble = None
        self.my_channel_id = None

        # Concurrency
        self.loop = asyncio.new_event_loop()
        self.queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _load_chime(self):
        """Handles loading the chime sound effect."""
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

                if os.path.exists('chime.raw'): os.remove('chime.raw')
                print(f"🔔 Chime loaded ({len(self.chime_pcm)} bytes)")
            except Exception as e:
                print(f"⚠️ Chime load error: {e}")

    def setup_mumble(self):
        print(f"🔌 Connecting to {config.SERVER_IP}...")
        self.mumble = pymumble.Mumble(config.SERVER_IP, config.BOT_USERNAME, password=config.PASSWORD, port=config.SERVER_PORT)

        # Callbacks
        self.mumble.callbacks.set_callback("user_updated", self.on_user_updated)
        # Delegate text handling to our new handler
        self.mumble.callbacks.set_callback("text_received", self.text_handler.handle)
        self.mumble.set_receive_sound(True)
        self.mumble.callbacks.set_callback("sound_received", self.on_sound_received)

    def run(self):
        print("🚀 Starting Bot...")
        threading.Thread(target=self._start_async_loop, daemon=True).start()

        while True:
            try:
                self.setup_mumble()
                self.mumble.start()
                self.mumble.is_ready()

                channel = self.mumble.channels.find_by_name(config.TARGET_CHANNEL)
                if channel: channel.move_in()

                print("✅ Connected!")

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

            with self.audio_lock:
                self.user_streams = {}

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
        while True:
            text = await self.queue.get()
            if self.mumble and self.mumble.sound_output:
                pcm_data = await self.loop.run_in_executor(self.executor, self.voice.generate_pcm, text)
                if pcm_data:
                    try: self.mumble.sound_output.add_sound(pcm_data)
                    except: pass
            self.queue.task_done()

    async def audio_processing_worker(self):
        while True:
            await asyncio.sleep(config.POLL_RATE)
            if not self.listening_enabled: continue

            now = time.time()
            with self.audio_lock:
                active_users = list(self.user_streams.keys())

            for name in active_users:
                if name in config.IGNORED_USERS: continue

                stream = self.user_streams[name]
                with stream.lock:
                    is_silence = (now - stream.last_packet_time) > config.SILENCE_THRESHOLD
                    has_data = len(stream.buffer) > 0

                if is_silence and has_data and not stream.is_processing:
                    raw_audio = stream.extract_audio()
                    if len(raw_audio) >= (48000 * 2 * config.MIN_AUDIO_LENGTH):
                        stream.is_processing = True
                        self.loop.run_in_executor(self.executor, self.process_voice_command, name, raw_audio, stream)

    def process_voice_command(self, user, raw_audio, stream):
        try:
            text = self.ear.transcribe(raw_audio)
            if text:
                print(f"[{user}]: {text}")
                # Delegate voice logic to handler
                self.voice_handler.handle(user, text)
        finally:
            stream.is_processing = False

    # --- CALLBACKS & HELPERS ---

    def say_async(self, text):
        """Helper to queue TTS from anywhere."""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, text)

    def send_chat(self, text):
        """Helper to send Mumble chat messages."""
        if self.mumble and self.my_channel_id is not None:
            try: self.mumble.channels[self.my_channel_id].send_text_message(text)
            except: pass

    def on_sound_received(self, user, sound_chunk):
        if not self.listening_enabled or not user: return
        if user['name'] in config.IGNORED_USERS: return

        with self.audio_lock:
            if user['name'] not in self.user_streams:
                self.user_streams[user['name']] = UserVoiceStream(user['name'])
            self.user_streams[user['name']].add_data(sound_chunk.pcm)

    def on_user_updated(self, user, mods):
        if "channel_id" not in mods: return
        name = user['name']

        if name == config.BOT_USERNAME or name in config.IGNORED_USERS: return

        new_ch = mods['channel_id']
        if new_ch == self.my_channel_id:
             self.say_async(f"Welcome {name}")

    def load_stats(self): pass
    def save_stats(self): pass
