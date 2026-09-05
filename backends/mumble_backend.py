"""Mumble backend — extracts the original pymumble code from bot.py.

No behavior change when USE_TEAMSPEAK=false. Keeps the exact callback
wiring: user_updated / text_received / sound_received, bandwidth clamp,
channel move, myself channel tracking.
"""
import config
from backends.base import VoiceBackend


class MumbleBackend(VoiceBackend):
    backend_name = "mumble"

    def __init__(self, bot):
        super().__init__(bot)
        self.mumble = None
        self._my_channel_id = None

    # -- lifecycle ------------------------------------------------------
    def connect(self):
        """Create pymumble client, register callbacks, start, join channel."""
        try:
            import pymumble_py3 as pymumble
        except ImportError as e:
            raise RuntimeError(
                "pymumble_py3 is required for the Mumble backend. "
                "Install it via `pip install -r requirements.txt`."
            ) from e

        logger = self.bot.logger
        logger.info(f"🔌 Connecting to {config.SERVER_IP}...")
        self.mumble = pymumble.Mumble(
            config.SERVER_IP,
            config.BOT_USERNAME,
            password=config.PASSWORD,
            port=config.SERVER_PORT,
        )

        # Callbacks — identical to the pre-refactor bot.setup_mumble()
        self.mumble.callbacks.set_callback("user_updated", self.bot.on_user_updated)
        self.mumble.callbacks.set_callback("text_received", self.bot.text_handler.handle)
        self.mumble.set_receive_sound(True)
        self.mumble.callbacks.set_callback("sound_received", self.bot.on_sound_received)

        self.mumble.start()
        self.mumble.is_ready()

        # Clamp outgoing audio bandwidth to prevent oversized Opus frames
        bandwidth = getattr(config, "MUMBLE_BANDWIDTH", 64000)
        try:
            self.mumble.set_bandwidth(bandwidth)
        except Exception as e:
            logger.warning(f"Could not set bandwidth: {e}")

        channel = self.mumble.channels.find_by_name(config.TARGET_CHANNEL)
        if channel:
            channel.move_in()
            logger.info(f"📍 Moved to channel: {config.TARGET_CHANNEL}")
        else:
            logger.warning(
                f"⚠️ Target channel '{config.TARGET_CHANNEL}' not found. "
                "Bot is in root channel."
            )

        self._sync_channel_id()
        # Keep legacy alias in sync (test compat + direct access)
        self.bot.mumble = self.mumble
        self.bot.my_channel_id = self._my_channel_id
        return self.mumble

    def disconnect(self):
        try:
            if self.mumble:
                try:
                    self.mumble.stop()
                except Exception:
                    pass
        finally:
            self.mumble = None
            if getattr(self.bot, "mumble", None) is not None:
                # Only clear alias if it points at our client
                try:
                    self.bot.mumble = None
                except Exception:
                    pass

    def is_alive(self):
        try:
            return bool(self.mumble and self.mumble.is_alive())
        except Exception:
            return False

    def sync(self):
        """Refresh cached my_channel_id from pymumble (call each tick)."""
        self._sync_channel_id()
        try:
            self.bot.my_channel_id = self._my_channel_id
        except Exception:
            pass

    def _sync_channel_id(self):
        try:
            if self.mumble and getattr(self.mumble, "users", None) and self.mumble.users.myself:
                self._my_channel_id = self.mumble.users.myself["channel_id"]
        except Exception:
            pass

    # -- chat / channel --------------------------------------------------
    def move_to_channel(self, name):
        if not self.mumble:
            return False
        try:
            channel = self.mumble.channels.find_by_name(name)
            if channel:
                channel.move_in()
                self._sync_channel_id()
                return True
            return False
        except Exception:
            return False

    def send_chat(self, text, target=None):
        if not self.mumble:
            return False
        try:
            cid = self._my_channel_id
            if cid is not None and hasattr(self.mumble, "channels"):
                self.mumble.channels[cid].send_text_message(text)
                return True
            return False
        except Exception:
            return False

    # -- audio ------------------------------------------------------------
    def play_pcm(self, pcm_bytes):
        if not pcm_bytes:
            return False
        if self.mumble and getattr(self.mumble, "sound_output", None):
            try:
                self.mumble.sound_output.add_sound(pcm_bytes)
                return True
            except Exception as e:
                try:
                    self.bot.logger.error(f"Error sending sound to mumble: {e}")
                except Exception:
                    pass
        return False

    def clear_audio_buffer(self):
        sound_output = getattr(getattr(self, "mumble", None), "sound_output", None)
        clear_buffer = getattr(sound_output, "clear_buffer", None)
        if callable(clear_buffer):
            try:
                clear_buffer()
                return True
            except Exception:
                pass
        return False

    # -- presence ----------------------------------------------------------
    def list_users(self):
        """Return [{name, id, channel}] from pymumble users dict."""
        users = []
        try:
            if not self.mumble or not getattr(self.mumble, "users", None):
                return users
            for _sid, u in self.mumble.users.items():
                try:
                    if isinstance(u, dict):
                        users.append(
                            {
                                "name": u.get("name"),
                                "id": _sid,
                                "channel": u.get("channel_id"),
                            }
                        )
                    else:
                        users.append(
                            {
                                "name": getattr(u, "name", str(u)),
                                "id": _sid,
                                "channel": getattr(u, "channel_id", None),
                            }
                        )
                except Exception:
                    continue
        except Exception:
            pass
        return users

    @property
    def my_channel_id(self):
        return self._my_channel_id

    def set_bandwidth(self, bandwidth):
        if self.mumble:
            try:
                self.mumble.set_bandwidth(bandwidth)
            except Exception as e:
                try:
                    self.bot.logger.warning(f"Could not set bandwidth: {e}")
                except Exception:
                    pass
