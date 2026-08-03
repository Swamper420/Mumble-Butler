import os
import sys
import subprocess
import time
import signal
import re
from datetime import datetime, timedelta
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

CLAUSE_DELIMITERS = re.compile(r'(?<=[.!?,\n;:—\-])\s+|(?<=\.\.\.)\s+|\n+')
WHITESPACE_RE = re.compile(r'\s+')

import pymumble_py3 as pymumble
import config

# Utilities
from utils import patch_ssl, setup_logger

# Modules
from modules.brain import Brain
from modules.ears import Ear
from modules.voice import Voice
from modules.audio_manager import AudioManager
from modules.wakeword import WakewordDetector
from modules.web_server import BotWebServer

# Logic Handlers
from handlers.text import TextHandler
from handlers.voice import VoiceHandler

import random

class MadnessBot:
    def __init__(self):
        # Initialize logging
        self.logger = setup_logger("MadnessBot")
        
        # Apply SSL patch for legacy/unverified connections
        patch_ssl()

        # Dependency check
        self._check_dependencies()

        # Initialize basic audio resources
        self._load_chime()

        # Core Modules
        self.brain = Brain()
        self.ear = Ear()
        self.voice = Voice()
        self.audio_manager = AudioManager(self)
        self.wakeword_detector = WakewordDetector()
        self.web_server = BotWebServer(self)

        # Logic Handlers
        self.text_handler = TextHandler(self)
        self.voice_handler = VoiceHandler(self)

        # Precache fast audio responses if enabled
        self.precached_wakeword_pcms = {}
        self.precached_action_pcms = {}
        self.precached_volume_pcms = {}
        self._precache_fast_audio_responses()

        # State
        self.listening_enabled = True
        self.mumble = None
        self.my_channel_id = None
        self.running = True

        self.start_time = time.time()

        # Concurrency
        self.loop = asyncio.new_event_loop()
        self.queue = asyncio.Queue()
        self.speech_generation = 0
        self.executor = ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 4)))

        self.recent_transcripts = []
        self.transcript_lock = threading.Lock()
        self.background_tasks = set()
        


        # Signal handling for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    def _check_dependencies(self):
        """Checks if required external tools are available."""
        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            self.logger.info("✅ ffmpeg found")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.warning("⚠️ ffmpeg not found. Chime loading and some audio features may fail.")

    def _handle_signal(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self.shutdown()

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
                self.logger.info(f"🔔 Chime loaded ({len(self.chime_pcm)} bytes)")
            except Exception as e:
                self.logger.error(f"⚠️ Chime load error: {e}")

    def _get_available_voices(self):
        """Returns a list of available voice IDs fetched from the external TTS API."""
        if hasattr(self, "voice") and self.voice:
            try:
                voices = self.voice.get_available_voices()
                if isinstance(voices, (list, set, tuple)) and len(voices) > 0:
                    return sorted(list(set(voices)))
            except Exception as e:
                self.logger.warning(f"Error fetching voices from TTS API: {e}")

        current_voice = getattr(getattr(self, "voice", None), "current_voice_id", None)
        default_voice = current_voice or getattr(config, "TTS_VOICE", "voice_fi")
        return [default_voice]


    def _precache_fast_audio_responses(self):
        """Generates or loads precached fast audio responses (wakewords, action confirmations, volume numbers) for all available voices."""
        import hashlib
        self.precached_wakeword_pcms = {}
        self.precached_action_pcms = {}
        self.precached_volume_pcms = {}

        if not getattr(config, "FAST_AUDIO_RESPONSES_ENABLED", False):
            return

        cache_dir = getattr(config, "FAST_AUDIO_CACHE_DIR", "data/precached_audio")
        available_voices = self._get_available_voices()
        self.logger.info(f"⚡ Pre-caching fast audio responses for {len(available_voices)} voice(s) (disk cache: {cache_dir})...")

        wakeword_phrases = getattr(config, "FAST_WAKEWORD_RESPONSES", [])
        action_map = getattr(config, "FAST_ACTION_CONFIRMATIONS", {})

        for voice_id in available_voices:
            v_wake_dir = os.path.join(cache_dir, voice_id, "wakewords")
            v_action_dir = os.path.join(cache_dir, voice_id, "actions")
            v_vol_dir = os.path.join(cache_dir, voice_id, "volume")
            os.makedirs(v_wake_dir, exist_ok=True)
            os.makedirs(v_action_dir, exist_ok=True)
            os.makedirs(v_vol_dir, exist_ok=True)

            self.precached_wakeword_pcms[voice_id] = []
            self.precached_action_pcms[voice_id] = {}
            self.precached_volume_pcms[voice_id] = {}

            # 1. Wakewords
            for phrase in wakeword_phrases:
                phrase_hash = hashlib.md5(phrase.encode("utf-8")).hexdigest()[:12]
                file_path = os.path.join(v_wake_dir, f"{phrase_hash}.pcm")
                pcm = None
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    try:
                        with open(file_path, "rb") as f:
                            pcm = f.read()
                    except Exception as e:
                        self.logger.warning(f"Error reading cached PCM '{file_path}': {e}")
                
                if not pcm:
                    try:
                        pcm = self.voice.generate_pcm(phrase, voice_id=voice_id)
                        if pcm:
                            with open(file_path, "wb") as f:
                                f.write(pcm)
                    except Exception as e:
                        self.logger.warning(f"Failed to generate wakeword response '{phrase}' for voice '{voice_id}': {e}")

                if pcm:
                    self.precached_wakeword_pcms[voice_id].append(pcm)

            # 2. Action Confirmations
            for category, phrase in action_map.items():
                file_path = os.path.join(v_action_dir, f"{category}.pcm")
                pcm = None
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    try:
                        with open(file_path, "rb") as f:
                            pcm = f.read()
                    except Exception as e:
                        self.logger.warning(f"Error reading cached action PCM '{file_path}': {e}")
                
                if not pcm:
                    try:
                        pcm = self.voice.generate_pcm(phrase, voice_id=voice_id)
                        if pcm:
                            with open(file_path, "wb") as f:
                                f.write(pcm)
                    except Exception as e:
                        self.logger.warning(f"Failed to generate action confirmation '{category}' for voice '{voice_id}': {e}")

                if pcm:
                    self.precached_action_pcms[voice_id][category] = pcm

            # 3. Volume Numbers (0..100)
            for level in range(0, 101):
                phrase = f"Volume {level}"
                file_path = os.path.join(v_vol_dir, f"{level}.pcm")
                pcm = None
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    try:
                        with open(file_path, "rb") as f:
                            pcm = f.read()
                    except Exception as e:
                        self.logger.warning(f"Error reading cached volume PCM '{file_path}': {e}")

                if not pcm:
                    try:
                        pcm = self.voice.generate_pcm(phrase, voice_id=voice_id)
                        if pcm:
                            with open(file_path, "wb") as f:
                                f.write(pcm)
                    except Exception as e:
                        self.logger.warning(f"Failed to generate volume PCM for '{level}' with voice '{voice_id}': {e}")

                if pcm:
                    self.precached_volume_pcms[voice_id][level] = pcm

        w_count = sum(len(v) for v in self.precached_wakeword_pcms.values())
        a_count = sum(len(v) for v in self.precached_action_pcms.values())
        v_count = sum(len(v) for v in self.precached_volume_pcms.values())
        self.logger.info(
            f"✅ Fast audio responses precached ({len(available_voices)} voice(s)): "
            f"{w_count} wake responses, {a_count} action confirmations, {v_count} volume responses."
        )

    def play_ack_sound(self):
        """
        Plays an acknowledgment sound. If fast audio responses are enabled and available,
        plays a randomly chosen fast wakeword response for the active voice. Otherwise falls back to chime_pcm.
        """
        if not (self.mumble and self.mumble.sound_output):
            return

        sound_to_play = None
        if getattr(config, "FAST_AUDIO_RESPONSES_ENABLED", False):
            current_voice = getattr(self.voice, "current_voice_id", config.CHATTERBOX_DEFAULT_VOICE)
            if isinstance(self.precached_wakeword_pcms, dict):
                voice_wakewords = self.precached_wakeword_pcms.get(current_voice, [])
                if not voice_wakewords and self.precached_wakeword_pcms:
                    first_key = next(iter(self.precached_wakeword_pcms))
                    voice_wakewords = self.precached_wakeword_pcms[first_key]
                if isinstance(voice_wakewords, list) and voice_wakewords:
                    sound_to_play = random.choice(voice_wakewords)
            elif isinstance(self.precached_wakeword_pcms, list) and self.precached_wakeword_pcms:
                sound_to_play = random.choice(self.precached_wakeword_pcms)

        if not sound_to_play and self.chime_pcm:
            sound_to_play = self.chime_pcm

        if sound_to_play:
            try:
                self.mumble.sound_output.add_sound(sound_to_play)
            except Exception as e:
                self.logger.error(f"Error playing ack sound: {e}")

    def play_action_confirmation(self, category, level=None):
        """
        Plays a precached action confirmation sound for a specific category (e.g. MUSIC, SEARCH, THINK, VOLUME).
        If category is VOLUME and level is provided, plays precached audio for that specific volume level if available.
        """
        if not (self.mumble and self.mumble.sound_output):
            return

        if not getattr(config, "FAST_AUDIO_RESPONSES_ENABLED", False):
            return

        current_voice = getattr(self.voice, "current_voice_id", config.CHATTERBOX_DEFAULT_VOICE)
        sound_to_play = None

        if category == "VOLUME" and level is not None:
            if isinstance(self.precached_volume_pcms, dict):
                voice_volumes = self.precached_volume_pcms.get(current_voice)
                if voice_volumes is None and self.precached_volume_pcms:
                    first_key = next(iter(self.precached_volume_pcms))
                    voice_volumes = self.precached_volume_pcms[first_key]
                if isinstance(voice_volumes, dict):
                    sound_to_play = voice_volumes.get(level)

        if not sound_to_play:
            if isinstance(self.precached_action_pcms, dict):
                if current_voice in self.precached_action_pcms and isinstance(self.precached_action_pcms[current_voice], dict):
                    sound_to_play = self.precached_action_pcms[current_voice].get(category)
                elif category in self.precached_action_pcms:
                    sound_to_play = self.precached_action_pcms.get(category)
                else:
                    first_val = next(iter(self.precached_action_pcms.values()), None)
                    if isinstance(first_val, dict):
                        sound_to_play = first_val.get(category)

        if sound_to_play:
            try:
                self.mumble.sound_output.add_sound(sound_to_play)
            except Exception as e:
                self.logger.error(f"Error playing action confirmation '{category}': {e}")

    def setup_mumble(self):
        """Initializes Mumble connection and callbacks."""
        self.logger.info(f"🔌 Connecting to {config.SERVER_IP}...")
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
        self.logger.info("🚀 Starting Bot...")
        threading.Thread(target=self._start_async_loop, daemon=True).start()

        # Start HTTP Web Interface Server
        self.web_server.start()

        # Connection / Reconnection Loop
        while self.running:
            try:
                self.setup_mumble()
                self.mumble.start()
                self.mumble.is_ready()

                channel = self.mumble.channels.find_by_name(config.TARGET_CHANNEL)
                if channel:
                    channel.move_in()

                self.logger.info("✅ Connected!")

                # Keep main thread alive while monitoring connection and child processes
                while self.running and self.mumble.is_alive():
                    if self.mumble.users.myself:
                        self.my_channel_id = self.mumble.users.myself['channel_id']

                    time.sleep(1)

                if self.running:
                    self.logger.warning("⚠️ Disconnected from server.")

            except Exception as e:
                if self.running:
                    self.logger.error(f"⚠️ Connection error: {e}")
            finally:
                if self.mumble:
                    try: self.mumble.stop()
                    except: pass

            if self.running:
                self.logger.info(f"🔄 Reconnecting in {config.RECONNECT_DELAY} seconds...")
                time.sleep(config.RECONNECT_DELAY)
                # Clear audio buffers on reconnect to prevent stale processing
                with self.audio_manager.lock:
                    self.audio_manager.user_streams.clear()

    def shutdown(self):
        self.logger.info("Shutting down...")
        self.running = False
        self.save_stats()

        self.web_server.stop()

        if self.mumble:
            self.mumble.stop()
        self.logger.info("Cleanup complete.")


    def _start_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(asyncio.gather(
            self.tts_worker(),
            self.audio_processing_worker(),
            self.hourly_report_worker()
        ))

    async def tts_worker(self):
        """Consumes text from queue and generates speech."""
        while True:
            speech_generation, text, user_name = await self.queue.get()
            if self.mumble and self.mumble.sound_output:
                pcm_data = await self.loop.run_in_executor(
                    self.executor,
                    self.voice.generate_pcm,
                    text,
                    None
                )
                if pcm_data and speech_generation == self.speech_generation:
                    try: self.mumble.sound_output.add_sound(pcm_data)
                    except: pass
            self.queue.task_done()

    async def audio_processing_worker(self):
        """Polls AudioManager for complete voice clips to process."""
        while True:
            await asyncio.sleep(config.POLL_RATE)
            if not self.listening_enabled: continue

            for user, raw_audio, stream in self.audio_manager.get_processable_audio():
                if user in config.IGNORED_USERS:
                    stream.is_processing = False
                    continue

                self.loop.run_in_executor(
                    self.executor,
                    self.process_voice_command,
                    user, raw_audio, stream
                )

    async def hourly_report_worker(self):
        """Announces status every hour."""
        self.logger.info("🕒 Hourly reporter started.")
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        seconds_until_hour = (next_hour - now).total_seconds()
        await asyncio.sleep(seconds_until_hour)

        while True:
            if self.mumble and self.mumble.users:
                active_users = [u['name'] for u in self.mumble.users.values()
                                if u['name'] not in config.IGNORED_USERS and u['name'] != config.BOT_USERNAME]

                if active_users:
                    one_minute_ago = time.time() - 60
                    with self.transcript_lock:
                        self.recent_transcripts = [t for t in self.recent_transcripts if t['time'] > one_minute_ago]
                        relevant_transcripts = self.recent_transcripts[:]

                    report = await self.loop.run_in_executor(
                        self.executor,
                        self.brain.generate_hourly_report,
                        active_users,
                        relevant_transcripts
                    )
                    if report:
                        self.say_async(report)
            await asyncio.sleep(3600)

    def process_voice_command(self, user, raw_audio, stream):
        """Transcribes audio and routes to VoiceHandler."""
        try:
            text = self.ear.transcribe(raw_audio)

            if text:
                self.logger.info(f"[{user}]: {text}")
                with self.transcript_lock:
                    self.recent_transcripts.append({
                        'time': time.time(),
                        'user': user,
                        'text': text
                    })
                self.voice_handler.handle(user, text)
        except Exception as e:
            self.logger.error(f"Error processing voice command: {e}")
        finally:
            stream.is_processing = False

    def schedule_reminder(self, seconds, message):
        def _schedule():
            try:
                if not hasattr(self, 'background_tasks'):
                    self.background_tasks = set()
                task = self.loop.create_task(self._async_reminder(seconds, message))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)
            except Exception as e:
                self.logger.error(f"CRITICAL ERROR in schedule_reminder: {e}")
        self.loop.call_soon_threadsafe(_schedule)

    async def _async_reminder(self, seconds, message):
        await asyncio.sleep(seconds)
        self.say_async(f"Reminder: {message}")

    def saysave_async(self, text, user=None):
        def _schedule():
            try:
                if not hasattr(self, 'background_tasks'):
                    self.background_tasks = set()
                task = self.loop.create_task(self._async_saysave(text, user))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)
            except Exception as e:
                self.logger.error(f"CRITICAL ERROR in saysave_async: {e}")
        self.loop.call_soon_threadsafe(_schedule)

    async def _async_saysave(self, text, user):
        import re
        import string
        import random
        from datetime import datetime

        cleaned = text.replace("\\n", " ").replace("/n", " ").replace("\\t", " ").replace("/t", " ")
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if not cleaned:
            self.send_chat("<b>Error:</b> Empty text provided for saysave.")
            return

        # Play the audio locally on the channel as well
        self.say_async(cleaned, user=user)

        # Generate the audio bytes
        try:
            pcm_data = await self.loop.run_in_executor(
                self.executor,
                self.voice.generate_pcm,
                cleaned,
                None
            )
        except Exception as e:
            self.logger.error(f"Error generating PCM for saysave: {e}")
            self.send_chat("<b>Error:</b> Failed to generate speech audio.")
            return

        if not pcm_data:
            self.send_chat("<b>Error:</b> Speech generation returned no audio data.")
            return

        try:
            # Ensure the directory exists
            save_dir = getattr(config, 'SAYSAVE_SAVE_DIR', "data/saysaves")
            os.makedirs(save_dir, exist_ok=True)

            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            filename = f"saysave_{timestamp}_{random_suffix}.m4a"
            output_path = os.path.join(save_dir, filename)
            abs_path = os.path.abspath(output_path)

            # Convert PCM to AAC M4A using ffmpeg
            cmd = [
                'ffmpeg', '-y',
                '-f', 's16le',
                '-ar', '48000',
                '-ac', '1',
                '-i', 'pipe:0',
                '-c:a', 'aac',
                output_path
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate(input=pcm_data)

            if proc.returncode == 0:
                self.send_chat(
                    f"🗣️ Voiceline saved to <b>data/saysaves/{filename}</b><br/>"
                    f"Path: <code>{abs_path}</code>"
                )
            else:
                self.logger.error(f"ffmpeg conversion failed with exit code {proc.returncode}")
                self.send_chat("<b>Error:</b> ffmpeg audio conversion failed.")
        except Exception as e:
            self.logger.error(f"Error saving voiceline: {e}")
            self.send_chat(f"<b>Error:</b> Failed to save voiceline: {e}")

    def say_async(self, text, user=None):
        speech_generation = self.speech_generation
        cleaned = text.replace("\\n", " ").replace("/n", " ").replace("\\t", " ").replace("/t", " ")
        cleaned = WHITESPACE_RE.sub(' ', cleaned).strip()
        if cleaned:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, (speech_generation, cleaned, user))

    def say_stream(self, prompt, user=None):
        speech_generation = self.speech_generation
        def _schedule():
            task = self.loop.create_task(self._tts_stream_worker(speech_generation, prompt, user))
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)
        self.loop.call_soon_threadsafe(_schedule)

    async def _tts_stream_worker(self, speech_generation, prompt, user):
        token_queue = asyncio.Queue()
        
        # Start LLM stream in executor
        self.loop.run_in_executor(
            self.executor,
            self.brain.generate_response_stream_async,
            prompt,
            token_queue,
            self.loop
        )

        full_response = []
        while True:
            token = await token_queue.get()
            if token is None:
                break
            if speech_generation != self.speech_generation:
                break
            full_response.append(token)

        if speech_generation == self.speech_generation:
            full_text = "".join(full_response).strip()
            if full_text:
                await self._generate_and_play_tts(speech_generation, full_text, user)

    async def _generate_and_play_tts(self, speech_generation, sentence, user):
        if self.mumble and self.mumble.sound_output:
            import re
            # Clean up literal formatting codes to prevent Kokoro from attempting to read them aloud
            cleaned_sentence = sentence.replace("\\n", " ").replace("/n", " ").replace("\\t", " ").replace("/t", " ")
            cleaned_sentence = re.sub(r'\s+', ' ', cleaned_sentence).strip()
            
            if not cleaned_sentence:
                return

            pcm_data = await self.loop.run_in_executor(
                self.executor,
                self.voice.generate_pcm,
                cleaned_sentence,
                None
            )

            if pcm_data and speech_generation == self.speech_generation:
                try:
                    self.mumble.sound_output.add_sound(pcm_data)
                except Exception as e:
                    self.logger.error(f"Error sending sound: {e}")


    def stop_speaking(self):
        self.speech_generation += 1
        def _clear_tts_queue():
            while True:
                try: self.queue.get_nowait()
                except asyncio.QueueEmpty: break
                else: self.queue.task_done()
        self.loop.call_soon_threadsafe(_clear_tts_queue)
        sound_output = getattr(getattr(self, "mumble", None), "sound_output", None)
        clear_buffer = getattr(sound_output, "clear_buffer", None)
        if callable(clear_buffer):
            try: clear_buffer()
            except: pass

    def send_chat(self, text):
        if self.mumble and self.my_channel_id is not None:
            try: self.mumble.channels[self.my_channel_id].send_text_message(text)
            except: pass

    def _send_music_command(self, command_key, argument=""):
        command = config.MUMBLE_COMMANDS[command_key]
        payload = command if not argument else f"{command} {argument}"
        self.send_chat(payload)
        return payload

    def play(self, query): return self._send_music_command("PLAY_YOUTUBE", query)
    def play_file(self, path): return self._send_music_command("FILE", path)
    def skip(self): return self._send_music_command("SKIP")
    def stop_music(self): return self._send_music_command("STOP")
    def pause_music(self): return self._send_music_command("PAUSE")
    def resume_music(self): return self._send_music_command("PLAY_GENERIC")
    def set_volume(self, level): return self._send_music_command("VOLUME", str(max(0, min(100, level))))
    def repeat_music(self, count): return self._send_music_command("REPEAT", str(max(0, count)))
    def set_mode(self, mode): return self._send_music_command("MODE", mode)
    def request_now_playing(self): return self._send_music_command("NOW_PLAYING")
    def request_queue(self): return self._send_music_command("QUEUE")
    def clear_queue(self): return self._send_music_command("CLEAR")

    def on_sound_received(self, user, sound_chunk):
        if not self.listening_enabled or not user: return
        if user['name'] in config.IGNORED_USERS: return
        self.audio_manager.add_audio(user['name'], sound_chunk.pcm)

    def on_user_updated(self, user, mods):
        if "channel_id" not in mods: return
        name = user['name']
        if name == config.BOT_USERNAME or name in config.IGNORED_USERS: return
        new_ch = mods['channel_id']
        if new_ch == self.my_channel_id:
             self.say_async(f"Welcome {name}", user=name)

    def get_status(self):
        """Returns a status report of the bot's components."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        status = {
            "Mumble": "Connected" if self.mumble and self.mumble.is_alive() else "Disconnected",
            "Uptime": uptime_str,
            "LLM": "Online" if self.brain.llm else "Offline",
            "STT": "Ready" if self.ear else "Error",
            "TTS": "Ready" if self.voice else "Error",
            "Wakeword": "Active" if self.wakeword_detector.enabled else "Bypassed",
            "Listening": "ON" if self.listening_enabled else "OFF",
            "Memory": "ON" if self.brain.memory_enabled else "OFF",
        }
        return status

    def load_stats(self): pass
    def save_stats(self): pass
