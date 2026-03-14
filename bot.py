import os
import subprocess
import time
from datetime import datetime, timedelta
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
        self.executor = ThreadPoolExecutor(max_workers=40)

        self.recent_transcripts = []
        self.transcript_lock = threading.Lock()
        self.background_tasks = set()

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
            self.audio_processing_worker(),
            self.hourly_report_worker()
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

    # NEW: Hourly Report Worker
    async def hourly_report_worker(self):
        """Announces status every hour."""
        print("🕒 Hourly reporter started.")

        # Wait until the next top-of-the-hour
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        seconds_until_hour = (next_hour - now).total_seconds()

        await asyncio.sleep(seconds_until_hour)

        while True:
            if self.mumble and self.mumble.users:
                # 1. Gather Context
                active_users = [u['name'] for u in self.mumble.users.values()
                                if u['name'] not in config.IGNORED_USERS and u['name'] != config.BOT_USERNAME]

                # 2. Get last minute of transcripts
                one_minute_ago = time.time() - 60
                relevant_transcripts = []
                with self.transcript_lock:
                    # Filter and cleanup old history
                    self.recent_transcripts = [t for t in self.recent_transcripts if t['time'] > one_minute_ago]
                    relevant_transcripts = self.recent_transcripts[:]

                # 3. Generate and Speak
                report = await self.loop.run_in_executor(
                    self.executor,
                    self.brain.generate_hourly_report,
                    active_users,
                    relevant_transcripts
                )
                if report:
                    self.say_async(report)

            # Wait for next hour
            await asyncio.sleep(3600)

    def process_voice_command(self, user, raw_audio, stream):
        """Transcribes audio and routes to VoiceHandler."""
        try:
            text = self.ear.transcribe(raw_audio)
            if text:
                print(f"[{user}]: {text}")
                with self.transcript_lock:
                    self.recent_transcripts.append({
                        'time': time.time(),
                        'user': user,
                        'text': text
                    })
                self.voice_handler.handle(user, text)
        except Exception as e:
            print(f"Error processing voice command: {e}")
        finally:
            stream.is_processing = False

    # --- PUBLIC HELPERS (Used by Handlers) ---

# ... inside MadnessBot class ...

# In bot.py

    def schedule_reminder(self, seconds, message):
        """Called from threads (VoiceHandler) to schedule an async task."""
        def _schedule():
            try:
                # Initialize storage if missing (Self-healing)
                if not hasattr(self, 'background_tasks'):
                    self.background_tasks = set()

                task = self.loop.create_task(self._async_reminder(seconds, message))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)
                print(f"DEBUG: Timer task created for {seconds}s.")
            except Exception as e:
                print(f"CRITICAL ERROR in schedule_reminder: {e}")

        self.loop.call_soon_threadsafe(_schedule)

    async def _async_reminder(self, seconds, message):
        print(f"⏳ Timer started: {seconds}s")
        await asyncio.sleep(seconds)
        print(f"⏰ Timer finished!")
        self.say_async(f"Reminder: {message}")

    def say_async(self, text):
        """Queues a message to be spoken by TTS."""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, text)

    def send_chat(self, text):
        """Sends a text message to the current Mumble channel."""
        if self.mumble and self.my_channel_id is not None:
            try: self.mumble.channels[self.my_channel_id].send_text_message(text)
            except: pass

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
