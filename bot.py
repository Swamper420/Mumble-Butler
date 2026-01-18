import os
import subprocess
import time
import re
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pymumble_py3 as pymumble
import config
from modules.audio_buffer import UserVoiceStream
from modules.brain import Brain
from modules.ears import Ear
from modules.voice import Voice

class MadnessBot:
    def __init__(self):
        self.user_stats = {}
        self.load_stats()

        self.chime_pcm = None
        if os.path.exists(config.CHIME_FILE):
            try:
                # Convert .wav to raw PCM using ffmpeg
                subprocess.run([
                    'ffmpeg', '-y', '-i', config.CHIME_FILE,
                    '-f', 's16le', '-acodec', 'pcm_s16le',
                    '-ar', '48000', '-ac', '1', 'chime.raw'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                # Read the raw bytes
                with open('chime.raw', 'rb') as f:
                    self.chime_pcm = f.read()

                # Cleanup
                if os.path.exists('chime.raw'):
                    os.remove('chime.raw')

                print(f"🔔 Chime loaded ({len(self.chime_pcm)} bytes)")
            except Exception as e:
                print(f"⚠️ Chime load error: {e}")

        # Modules
        self.brain = Brain()
        self.ear = Ear()
        self.voice = Voice()

        # State
        self.listening_enabled = True
        self.user_streams = {}
        self.audio_lock = threading.Lock()
        self.announcement_cooldown = {}

        # Concurrency
        self.loop = asyncio.new_event_loop()
        self.queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Mumble Setup
        self.mumble = pymumble.Mumble(config.SERVER_IP, config.BOT_USERNAME, password=config.PASSWORD, port=config.SERVER_PORT)
        self.mumble.callbacks.set_callback("user_updated", self.on_user_updated)
        self.mumble.callbacks.set_callback("text_received", self.on_text_received)
        self.mumble.set_receive_sound(True)
        self.mumble.callbacks.set_callback("sound_received", self.on_sound_received)

        self.my_channel_id = None

    def run(self):
        print("🚀 Starting Bot...")
        threading.Thread(target=self._start_async_loop, daemon=True).start()

        self.mumble.start()
        self.mumble.is_ready()

        channel = self.mumble.channels.find_by_name(config.TARGET_CHANNEL)
        if channel: channel.move_in()

        try:
            while True:
                if self.mumble.users.myself:
                    self.my_channel_id = self.mumble.users.myself['channel_id']
                time.sleep(1)
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self):
        print("\nShutting down...")
        self.save_stats()
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
            pcm_data = await self.loop.run_in_executor(self.executor, self.voice.generate_pcm, text)
            if pcm_data:
                self.mumble.sound_output.add_sound(pcm_data)
            self.queue.task_done()

    async def audio_processing_worker(self):
        while True:
            await asyncio.sleep(config.POLL_RATE)
            if not self.listening_enabled: continue

            now = time.time()
            with self.audio_lock:
                active_users = list(self.user_streams.keys())

            for name in active_users:
                # Double check to ensure we don't process ignored users who might have slipped in
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
                self.handle_logic(user, text)
        finally:
            stream.is_processing = False

    def handle_logic(self, user, text):
        clean = re.sub(r'[^\w\s]', '', text).lower().strip()
        keyword_regex = r"^" + re.escape(config.ACTIVATION_KEYWORD) + r"\b"

        if not re.search(keyword_regex, clean): return
        content = re.sub(keyword_regex, "", clean).strip()

        if self.chime_pcm:
            self.mumble.sound_output.add_sound(self.chime_pcm)

        cmd_out = None

        # --- Voice Command Processing using Config ---

        # 1. Forget
        if any(w in content for w in config.VOICE_TRIGGERS['FORGET']):
            self.brain.reset_memory()
            self.say_async("Memory wiped.")
            return

        # 2. Volume
        if any(w in content for w in config.VOICE_TRIGGERS['VOLUME']) and (m := re.search(r"(\d+)", content)):
            cmd_out = f"{config.MUMBLE_COMMANDS['VOLUME']} {m.group(1)}"

        # 3. Recommend (Moved up priority)
        elif any(w in content for w in config.VOICE_TRIGGERS['RECOMMEND']):
            triggers = config.VOICE_TRIGGERS['RECOMMEND']
            desc = content
            for t in triggers:
                desc = desc.replace(t, "")

            desc = desc.strip() or "random music"
            song = self.brain.recommend_song(desc)
            if song:
                cmd_out = f"{config.MUMBLE_COMMANDS['PLAY_YOUTUBE']} {song}"
                self.say_async(f"Queued {song}")

        # 4. Play / Queue
        elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_MUSIC']):
             # If "music" is triggered explicitly -> !play
             cmd_out = config.MUMBLE_COMMANDS['PLAY_GENERIC']

        elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_SPECIFIC']):
            # Check for generic "play [song]" or "queue [song]"
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_SPECIFIC'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                cmd_out = f"{config.MUMBLE_COMMANDS['PLAY_YOUTUBE']} {q.group(1)}"

        # 5. Stop / Pause
        elif any(w in content for w in config.VOICE_TRIGGERS['STOP']):
            cmd_out = config.MUMBLE_COMMANDS['PAUSE']

        # 6. Skip / Next
        elif any(w in content for w in config.VOICE_TRIGGERS['SKIP']):
            cmd_out = config.MUMBLE_COMMANDS['SKIP']

        # 7. File (New)
        elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_FILE']):
            # Matches: "file <path>", "f <path>", "file <keyword>"
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_FILE'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                # Sends: !file <arg>
                cmd_out = f"{config.MUMBLE_COMMANDS['FILE']} {q.group(1)}"

        # 8. Repeat (New)
        elif any(w in content for w in config.VOICE_TRIGGERS['REPEAT']):
            # Matches: "repeat", "repeat 5", "loop 3"
            m = re.search(r"(\d+)", content)
            # Default to 1 if no number is spoken
            count = m.group(1) if m else "1"
            cmd_out = f"{config.MUMBLE_COMMANDS['REPEAT']} {count}"

        # Execution
        if cmd_out:
            self.send_chat(cmd_out)
        else:
            response = self.brain.generate_response(f"User {user} says: {content}")
            self.say_async(response)

    # --- CALLBACKS & HELPERS ---

    def say_async(self, text):
        self.loop.call_soon_threadsafe(self.queue.put_nowait, text)

    def send_chat(self, text):
        try: self.mumble.channels[self.my_channel_id].send_text_message(text)
        except: pass

    def on_sound_received(self, user, sound_chunk):
        if not self.listening_enabled or not user: return

        # --- IGNORED USER CHECK ---
        if user['name'] in config.IGNORED_USERS: return
        # --------------------------

        with self.audio_lock:
            if user['name'] not in self.user_streams:
                self.user_streams[user['name']] = UserVoiceStream(user['name'])
            self.user_streams[user['name']].add_data(sound_chunk.pcm)

    def on_text_received(self, message):
            # 1. Resolve User from ID
            sender_id = message.actor

            # If the user isn't in our list (rare race condition), ignore
            if sender_id not in self.mumble.users:
                return

            sender = self.mumble.users[sender_id]

            # 2. Safety Checks
            if not sender or sender_id == self.mumble.users.myself_session:
                return

            if sender['name'] in config.IGNORED_USERS:
                return

            text = message.message.strip()

            # 3. Parse Command
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            # --- Text Command Processing using Config ---

            # Help
            if cmd == config.TEXT_TRIGGERS['HELP']:
                # Dynamically list commands
                cmds = ", ".join(config.TEXT_TRIGGERS.values())
                self.send_chat(f"Commands: {cmds}, ?voice [name]")

            # Listen Toggle
            elif cmd == config.TEXT_TRIGGERS['LISTEN']:
                self.listening_enabled = not self.listening_enabled
                status = "ON" if self.listening_enabled else "OFF"
                self.send_chat(f"Listening: {status}")

            # Forget Memory
            elif cmd == config.TEXT_TRIGGERS['FORGET']:
                self.brain.reset_memory()
                self.send_chat("Memory wiped.")

            # Voice Change
            elif cmd == config.TEXT_TRIGGERS['VOICE']:
                if arg.lower() in config.AVAILABLE_VOICES:
                    new_voice_id = config.AVAILABLE_VOICES[arg.lower()]
                    self.voice.current_voice_id = new_voice_id
                    self.send_chat(f"Voice changed to: {arg}")
                else:
                    voices_list = ", ".join(config.AVAILABLE_VOICES.keys())
                    self.send_chat(f"Available voices: {voices_list}")

            # Say (TTS Echo)
            elif cmd == config.TEXT_TRIGGERS['SAY']:
                if arg:
                    self.say_async(arg)

    def on_user_updated(self, user, mods):
        if "channel_id" not in mods: return
        name = user['name']

        # --- IGNORED USER CHECK ---
        if name == config.BOT_USERNAME or name in config.IGNORED_USERS: return
        # --------------------------

        new_ch = mods['channel_id']
        if new_ch == self.my_channel_id:
             self.say_async(f"Welcome {name}")

    def load_stats(self):
        pass

    def save_stats(self):
        pass
