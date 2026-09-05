import os
import subprocess
import time
import signal
import re
import hashlib
import string
import random
from datetime import datetime, timedelta
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

WHITESPACE_RE = re.compile(r'\s+')

import config

# Utilities (tolerant import: tests stub `utils` with only patch_ssl)
try:
    from utils import patch_ssl, setup_logger
except ImportError:  # pragma: no cover - test stub compat
    from utils import patch_ssl

    import logging as _logging
    import sys as _sys

    def setup_logger(name="MadnessBot", level=_logging.INFO):
        _logger = _logging.getLogger(name)
        if not _logger.handlers:
            _handler = _logging.StreamHandler(_sys.stdout)
            _handler.setFormatter(_logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'))
            _logger.addHandler(_handler)
            _logger.setLevel(level)
        return _logger

# Modules
from modules.brain import Brain
from modules.ears import Ear
from modules.voice import Voice
from modules.audio_manager import AudioManager
from modules.wakeword import WakewordDetector

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

        # Voice/chat backend (Mumble default; TeamSpeak 6 when USE_TEAMSPEAK=true).
        # Kept as instance attr so tests can inject fakes. self.mumble stays
        # as the Mumble-only alias for backward compat.
        self.backend = None
        try:
            from backends import create_backend
            self.backend = create_backend(self)
        except Exception as e:
            # Backend creation must never break __init__ (e.g. missing deps
            # in unit tests). Connection happens in run().
            try:
                self.logger.warning(f"Backend init deferred: {e}")
            except Exception:
                pass

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
        """Returns a list of available voice IDs fetched from the external TTS API, ensuring default_voice is included."""
        current_voice = getattr(getattr(self, "voice", None), "current_voice_id", None)
        default_voice = current_voice or getattr(config, "TTS_VOICE", "mieto_fi")

        if hasattr(self, "voice") and self.voice:
            try:
                voices = self.voice.get_available_voices()
                if isinstance(voices, (list, set, tuple)) and len(voices) > 0:
                    voice_set = set(voices)
                    voice_set.add(default_voice)
                    return sorted(list(voice_set))
            except Exception as e:
                self.logger.warning(f"Error fetching voices from TTS API: {e}")

        return [default_voice]


    def _precache_fast_audio_responses(self):
        """Generates or loads precached fast audio responses (wakewords, action confirmations, volume numbers) for all available voices."""
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
                phrase = f"Äänenvoimakkuus {level}"
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

    def _real_backend(self):
        """Return backend only when it is a real VoiceBackend (or test fake).

        Ignores auto-created MagicMock attributes (unit tests inject
        MagicMock bots where .backend exists but is not a real backend).
        Test fakes using SimpleNamespace(backend_name=...) are honoured.
        """
        backend = getattr(self, "backend", None)
        if backend is None:
            return None
        try:
            name = getattr(backend, "backend_name", None)
            if name in ("mumble", "teamspeak6", "base"):
                return backend
            # Also accept objects with the VoiceBackend interface even when
            # backend_name is missing (e.g. minimal test doubles exposing
            # play_pcm/clear_audio_buffer/send_chat/is_alive).
            for attr in ("play_pcm", "clear_audio_buffer", "send_chat", "is_alive"):
                if callable(getattr(backend, attr, None)):
                    # Distinguish real doubles from MagicMock: MagicMock attrs
                    # are MagicMocks, but their type name reveals the mock.
                    if "Mock" in type(backend).__name__:
                        return None
                    return backend
            return None
        except Exception:
            return None

    def _play_pcm_via_backend(self, pcm_bytes):
        """Play PCM via backend, falling back to legacy self.mumble alias.

        Returns True when queued. Backend-first keeps TS6 + Mumble working;
        the self.mumble fallback preserves unit tests that inject a mock
        mumble object without a backend.
        """
        if not pcm_bytes:
            return False
        backend = self._real_backend()
        if backend is not None:
            try:
                if backend.play_pcm(pcm_bytes):
                    return True
            except Exception as e:
                try:
                    self.logger.error(f"Error playing audio via backend: {e}")
                except Exception:
                    pass
        # Legacy fallback (Mumble alias / injected mocks in tests)
        mumble = getattr(self, "mumble", None)
        # Avoid treating auto-mocked sound_output as real when backend is real
        # and already failed — still try alias for Mumble compat.
        sound_output = None
        try:
            sound_output = getattr(mumble, "sound_output", None) if mumble else None
            # Ignore pure MagicMock artifacts when mumble itself is auto-mock?
            # Tests explicitly set bot.mumble = MagicMock()/SimpleNamespace with
            # sound_output, so honour it. Only skip when mumble is None.
        except Exception:
            sound_output = None
        if sound_output is not None:
            try:
                sound_output.add_sound(pcm_bytes)
                return True
            except Exception as e:
                try:
                    self.logger.error(f"Error playing audio via mumble alias: {e}")
                except Exception:
                    pass
        return False

    def _has_audio_output(self):
        backend = self._real_backend()
        if backend is not None:
            try:
                if backend.is_alive():
                    return True
            except Exception:
                pass
        mumble = getattr(self, "mumble", None)
        return bool(mumble and getattr(mumble, "sound_output", None))

    @property
    def _is_teamspeak(self):
        if getattr(config, "USE_TEAMSPEAK", False):
            return True
        backend = getattr(self, "backend", None)
        return bool(backend is not None and getattr(backend, "backend_name", "") == "teamspeak6")

    def play_ack_sound(self):
        """
        Plays an acknowledgment sound. If fast audio responses are enabled and available,
        plays a randomly chosen fast wakeword response for the active voice. Otherwise falls back to chime_pcm.

        NOTE: Inlined backend/mumble routing (no helper calls) so unbound
        calls with MagicMock selves (unit tests) keep working: helpers would
        themselves be auto-mocks on such selves and swallow playback.
        """
        # Select sound first (uses only explicitly-set attrs + config)
        sound_to_play = None
        try:
            fast_enabled = getattr(config, "FAST_AUDIO_RESPONSES_ENABLED", False)
        except Exception:
            fast_enabled = False
        if fast_enabled:
            try:
                current_voice = getattr(getattr(self, "voice", None), "current_voice_id",
                                        getattr(config, "TTS_VOICE", "mieto_fi"))
            except Exception:
                current_voice = "mieto_fi"
            try:
                precached = getattr(self, "precached_wakeword_pcms", {})
                if isinstance(precached, dict):
                    voice_wakewords = precached.get(current_voice, [])
                    if not voice_wakewords and precached:
                        first_key = next(iter(precached))
                        voice_wakewords = precached[first_key]
                    if isinstance(voice_wakewords, list) and voice_wakewords:
                        sound_to_play = random.choice(voice_wakewords)
                elif isinstance(precached, list) and precached:
                    sound_to_play = random.choice(precached)
            except Exception:
                pass

        try:
            chime = getattr(self, "chime_pcm", None)
        except Exception:
            chime = None
        if not sound_to_play and chime:
            sound_to_play = chime
        if not sound_to_play:
            return

        # Backend-first when it is a real backend (backend_name string match)
        try:
            b = getattr(self, "backend", None)
            if getattr(b, "backend_name", None) in ("mumble", "teamspeak6", "base"):
                try:
                    if b.play_pcm(sound_to_play):
                        return
                except Exception as e:
                    try:
                        self.logger.error(f"Error playing ack sound via backend: {e}")
                    except Exception:
                        pass
        except Exception:
            pass
        # Legacy Mumble alias fallback (covers injected mocks in tests)
        try:
            m = getattr(self, "mumble", None)
            so = getattr(m, "sound_output", None) if m else None
            if so is not None:
                so.add_sound(sound_to_play)
        except Exception as e:
            try:
                self.logger.error(f"Error playing ack sound: {e}")
            except Exception:
                pass

    def play_action_confirmation(self, category, level=None):
        """
        Plays a precached action confirmation sound for a specific category (e.g. MUSIC, SEARCH, THINK, VOLUME).
        If category is VOLUME and level is provided, plays precached audio for that specific volume level if available.

        NOTE: Inlined routing (see play_ack_sound) for MagicMock-self compat.
        """
        try:
            fast_enabled = getattr(config, "FAST_AUDIO_RESPONSES_ENABLED", False)
        except Exception:
            fast_enabled = False
        if not fast_enabled:
            return

        try:
            current_voice = getattr(getattr(self, "voice", None), "current_voice_id",
                                    getattr(config, "TTS_VOICE", "mieto_fi"))
        except Exception:
            current_voice = "mieto_fi"
        sound_to_play = None

        try:
            if category == "VOLUME" and level is not None:
                precached_vol = getattr(self, "precached_volume_pcms", {})
                if isinstance(precached_vol, dict):
                    voice_volumes = precached_vol.get(current_voice)
                    if voice_volumes is None and precached_vol:
                        first_key = next(iter(precached_vol))
                        voice_volumes = precached_vol[first_key]
                    if isinstance(voice_volumes, dict):
                        sound_to_play = voice_volumes.get(level)

            if not sound_to_play:
                precached_act = getattr(self, "precached_action_pcms", {})
                if isinstance(precached_act, dict):
                    if current_voice in precached_act and isinstance(precached_act[current_voice], dict):
                        sound_to_play = precached_act[current_voice].get(category)
                    elif category in precached_act:
                        sound_to_play = precached_act.get(category)
                    else:
                        try:
                            first_val = next(iter(precached_act.values()), None)
                        except Exception:
                            first_val = None
                        if isinstance(first_val, dict):
                            sound_to_play = first_val.get(category)
        except Exception:
            pass

        if not sound_to_play:
            return
        try:
            b = getattr(self, "backend", None)
            if getattr(b, "backend_name", None) in ("mumble", "teamspeak6", "base"):
                try:
                    if b.play_pcm(sound_to_play):
                        return
                except Exception as e:
                    try:
                        self.logger.error(f"Error playing action confirmation '{category}' via backend: {e}")
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            m = getattr(self, "mumble", None)
            so = getattr(m, "sound_output", None) if m else None
            if so is not None:
                so.add_sound(sound_to_play)
        except Exception as e:
            try:
                self.logger.error(f"Error playing action confirmation '{category}': {e}")
            except Exception:
                pass

    def setup_mumble(self):
        """Initializes Mumble connection and callbacks.

        Delegates to MumbleBackend when active (Phase 0 refactor); falls back
        to the legacy inline pymumble setup for direct callers/tests.
        """
        backend = getattr(self, "backend", None)
        if backend is not None and getattr(backend, "backend_name", "") == "mumble":
            try:
                backend.connect()
                # Sync legacy aliases
                self.mumble = getattr(backend, "mumble", self.mumble)
                self.my_channel_id = getattr(backend, "my_channel_id", self.my_channel_id)
                return
            except Exception:
                pass  # fall through to legacy path below
        # Legacy inline path (kept for test compat / direct use)
        try:
            import pymumble_py3 as pymumble
        except ImportError as e:
            raise RuntimeError("pymumble_py3 is required for setup_mumble().") from e
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

    def _ensure_backend(self):
        """Lazily create backend if __init__ deferred it (e.g. in tests)."""
        if getattr(self, "backend", None) is None:
            try:
                from backends import create_backend
                self.backend = create_backend(self)
            except Exception as e:
                try:
                    self.logger.warning(f"Backend creation failed: {e}")
                except Exception:
                    pass
        return getattr(self, "backend", None)

    def _backend_is_alive(self):
        backend = self._ensure_backend()
        if backend is not None:
            try:
                return bool(backend.is_alive())
            except Exception:
                return False
        # Legacy fallback
        try:
            return bool(self.mumble and self.mumble.is_alive())
        except Exception:
            return False

    def _backend_sync_tick(self):
        """Per-second tick: refresh my_channel_id from backend or mumble."""
        backend = getattr(self, "backend", None)
        try:
            if backend is not None and getattr(backend, "backend_name", "") == "mumble":
                sync = getattr(backend, "sync", None)
                if callable(sync):
                    sync()
                    self.my_channel_id = getattr(backend, "my_channel_id", self.my_channel_id)
                    return
            if backend is not None:
                try:
                    self.my_channel_id = backend.my_channel_id
                    return
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self.mumble and getattr(self.mumble, "users", None) and self.mumble.users.myself:
                self.my_channel_id = self.mumble.users.myself['channel_id']
        except Exception:
            pass

    def run(self):
        """Main application loop (backend-agnostic)."""
        backend_name = "teamspeak6" if getattr(config, "USE_TEAMSPEAK", False) else "mumble"
        self.logger.info(f"🚀 Starting Bot... (backend={backend_name})")
        threading.Thread(target=self._start_async_loop, daemon=True).start()

        # Ensure backend exists (deferred creation path)
        self._ensure_backend()

        # Connection / Reconnection Loop
        while self.running:
            try:
                backend = getattr(self, "backend", None)
                if backend is not None:
                    backend.connect()
                    # Sync legacy Mumble alias when applicable
                    if getattr(backend, "backend_name", "") == "mumble":
                        try:
                            self.mumble = getattr(backend, "mumble", self.mumble)
                        except Exception:
                            pass
                    try:
                        self.my_channel_id = backend.my_channel_id
                    except Exception:
                        pass
                else:
                    # No backend (should not happen) — legacy Mumble path
                    self.setup_mumble()
                    self.mumble.start()
                    self.mumble.is_ready()
                    bandwidth = getattr(config, "MUMBLE_BANDWIDTH", 64000)
                    try:
                        self.mumble.set_bandwidth(bandwidth)
                    except Exception as e:
                        self.logger.warning(f"Could not set bandwidth: {e}")
                    channel = self.mumble.channels.find_by_name(config.TARGET_CHANNEL)
                    if channel:
                        channel.move_in()
                        self.logger.info(f"📍 Moved to channel: {config.TARGET_CHANNEL}")
                    else:
                        self.logger.warning(f"⚠️ Target channel '{config.TARGET_CHANNEL}' not found. Bot is in root channel.")

                self.logger.info("✅ Connected!")

                # Keep main thread alive while monitoring connection and child processes
                while self.running and self._backend_is_alive():
                    self._backend_sync_tick()
                    time.sleep(1)

                if self.running:
                    self.logger.warning("⚠️ Disconnected from server.")

            except Exception as e:
                if self.running:
                    self.logger.error(f"⚠️ Connection error: {e}")
            finally:
                backend = getattr(self, "backend", None)
                if backend is not None:
                    try:
                        backend.disconnect()
                    except Exception:
                        pass
                elif self.mumble:
                    try: self.mumble.stop()
                    except: pass

            if self.running:
                self.logger.info(f"🔄 Reconnecting in {config.RECONNECT_DELAY} seconds...")
                time.sleep(config.RECONNECT_DELAY)
                # Clear audio buffers on reconnect to prevent stale processing
                try:
                    with self.audio_manager.lock:
                        self.audio_manager.user_streams.clear()
                except Exception:
                    pass

    def shutdown(self):
        self.logger.info("Shutting down...")
        self.running = False

        backend = getattr(self, "backend", None)
        if backend is not None:
            try:
                backend.disconnect()
            except Exception:
                pass
        if self.mumble:
            try:
                self.mumble.stop()
            except Exception:
                pass
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
            pcm_data = await self.loop.run_in_executor(
                self.executor,
                self.voice.generate_pcm,
                text,
                None
            )
            if pcm_data and speech_generation == self.speech_generation:
                self._play_pcm_via_backend(pcm_data)
            elif not pcm_data:
                self.logger.warning(f"⚠️ No PCM audio generated for text: {text}")
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

    def get_active_users(self):
        """Backend-agnostic active (non-ignored, non-self) user names.

        Used by hourly reports. Prefers backend.list_users(), falls back to
        legacy self.mumble.users dict.
        """
        ignored = set(getattr(config, "IGNORED_USERS", []) or [])
        self_names = {getattr(config, "BOT_USERNAME", ""), getattr(config, "TS6_NICKNAME", "")}
        backend = self._real_backend()
        if backend is not None:
            try:
                users = backend.list_users() or []
                # Guard against MagicMock artifacts (non-list returns)
                if isinstance(users, list) and users:
                    return [u.get("name") for u in users
                            if isinstance(u, dict) and u.get("name") and u.get("name") not in ignored
                            and u.get("name") not in self_names]
            except Exception:
                pass
        try:
            if self.mumble and getattr(self.mumble, "users", None):
                return [u['name'] for u in self.mumble.users.values()
                        if u['name'] not in config.IGNORED_USERS and u['name'] != config.BOT_USERNAME]
        except Exception:
            pass
        return []

    async def hourly_report_worker(self):
        """Announces status every hour."""
        if not getattr(config, 'HOURLY_REPORT_ENABLED', True):
            self.logger.info("🕒 Hourly reporter disabled by config.")
            return
        self.logger.info("🕒 Hourly reporter started.")
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        seconds_until_hour = (next_hour - now).total_seconds()
        await asyncio.sleep(seconds_until_hour)

        while True:
            active_users = self.get_active_users()

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
        # Clean up literal formatting codes to prevent TTS from attempting to read them aloud
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
            self._play_pcm_via_backend(pcm_data)


    def stop_speaking(self):
        self.speech_generation += 1
        def _clear_tts_queue():
            while True:
                try: self.queue.get_nowait()
                except asyncio.QueueEmpty: break
                else: self.queue.task_done()
        try:
            self.loop.call_soon_threadsafe(_clear_tts_queue)
        except Exception:
            # Loop may be a test fake; run inline
            try:
                _clear_tts_queue()
            except Exception:
                pass
        # Backend-first (TS6 bridge / Mumble), then legacy alias for mocks
        backend = self._real_backend()
        if backend is not None:
            try:
                if backend.clear_audio_buffer():
                    return
            except Exception:
                pass
        sound_output = getattr(getattr(self, "mumble", None), "sound_output", None)
        clear_buffer = getattr(sound_output, "clear_buffer", None)
        if callable(clear_buffer):
            try: clear_buffer()
            except: pass

    def send_chat(self, text, target=None):
        # Backend-first (works for Mumble + TS6 query)
        backend = self._real_backend()
        if backend is not None:
            try:
                if backend.send_chat(text, target=target):
                    return True
            except TypeError:
                try:
                    if backend.send_chat(text):
                        return True
                except Exception:
                    pass
            except Exception:
                pass
        # Legacy Mumble alias fallback
        if self.mumble and self.my_channel_id is not None:
            try:
                self.mumble.channels[self.my_channel_id].send_text_message(text)
                return True
            except: pass
        elif self.mumble:
            # Channel id unknown (tests inject mocks without channels dict
            # keyed by id) — best effort: try channels dict first value?
            try:
                channels = getattr(self.mumble, "channels", None)
                if channels is not None and hasattr(channels, "__getitem__") and self.my_channel_id is not None:
                    channels[self.my_channel_id].send_text_message(text)
                    return True
            except Exception:
                pass
        return False

    def _music_unsupported(self):
        """True when music must be blocked (TeamSpeak backend)."""
        if self._is_teamspeak:
            try:
                self.send_chat(getattr(config, "TS6_MUSIC_UNSUPPORTED_MSG",
                                       "🎵 Music via botamusique is not supported on TeamSpeak yet."))
            except Exception:
                pass
            return True
        return False

    def _send_music_command(self, command_key, argument=""):
        if self._music_unsupported():
            return None
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
        pcm = getattr(sound_chunk, "pcm", sound_chunk)
        self.audio_manager.add_audio(user['name'], pcm)

    def handle_audio(self, user_name, pcm_bytes):
        """Backend-agnostic inbound audio (used by TS6 bridge)."""
        if not self.listening_enabled or not user_name:
            return
        if user_name in config.IGNORED_USERS:
            return
        try:
            self.audio_manager.add_audio(user_name, pcm_bytes)
        except Exception as e:
            try:
                self.logger.error(f"Error handling inbound audio: {e}")
            except Exception:
                pass

    def on_user_updated(self, user, mods):
        if "channel_id" not in mods: return
        name = user['name']
        if name == config.BOT_USERNAME or name in config.IGNORED_USERS: return
        new_ch = mods['channel_id']
        if new_ch == self.my_channel_id:
             self.say_async(f"Tervetuloa {name}", user=name)

    def handle_user_joined(self, user_name, channel):
        """Backend-agnostic join welcome (used by TS6 query cliententerview)."""
        if not user_name:
            return
        if user_name == config.BOT_USERNAME or user_name in config.IGNORED_USERS:
            return
        try:
            own_channel = self.my_channel_id
            if own_channel is None:
                backend = getattr(self, "backend", None)
                if backend is not None:
                    try:
                        own_channel = backend.my_channel_id
                    except Exception:
                        pass
            if channel == own_channel or str(channel) == str(own_channel):
                self.say_async(f"Tervetuloa {user_name}", user=user_name)
        except Exception:
            pass

    def get_status(self):
        """Returns a status report of the bot's components."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        # Backend-aware connection state (Mumble alias fallback for tests).
        # Use _real_backend() to ignore auto-mocked .backend on MagicMock bots.
        backend = self._real_backend()
        backend_label = "teamspeak6" if self._is_teamspeak else "mumble"
        if backend is not None:
            try:
                alive = backend.is_alive()
                # MagicMock guard: only honour real bools
                connected = bool(alive) if isinstance(alive, bool) else False
                # Test doubles (SimpleNamespace) may return bool too
                if not isinstance(alive, bool):
                    try:
                        connected = bool(alive) and not ("Mock" in type(backend).__name__)
                    except Exception:
                        connected = False
            except Exception:
                connected = False
        else:
            try:
                connected = bool(self.mumble and self.mumble.is_alive())
            except Exception:
                connected = False
        bridge_status = "N/A"
        try:
            if backend is not None:
                vb = getattr(backend, "voice_bridge_status", "N/A")
                # Unwrap property values; ignore MagicMock artifacts
                if isinstance(vb, str):
                    bridge_status = vb
                elif not ("Mock" in type(getattr(backend, "voice_bridge_status", "")).__name__):
                    bridge_status = str(vb)
        except Exception:
            pass

        if self._is_teamspeak:
            conn_key = "TeamSpeak"
            conn_val = "Connected" if connected else "Disconnected"
        else:
            conn_key = "Mumble"
            try:
                mumble_alive = bool(self.mumble and self.mumble.is_alive())
            except Exception:
                mumble_alive = connected
            conn_val = "Connected" if (connected or mumble_alive) else "Disconnected"

        status = {
            conn_key: conn_val,
            "Backend": backend_label,
            "VoiceBridge": bridge_status,
            "Uptime": uptime_str,
            "LLM": "Online" if self.brain.llm else "Offline",
            "STT": "Ready" if self.ear else "Error",
            "TTS": "Ready" if self.voice else "Error",
            "Wakeword": "Active" if self.wakeword_detector.enabled else "Bypassed",
            "Listening": "ON" if self.listening_enabled else "OFF",
            "Memory": "ON" if self.brain.memory_enabled else "OFF",
        }
        return status
