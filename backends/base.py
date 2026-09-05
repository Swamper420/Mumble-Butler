"""VoiceBackend ABC — common contract for Mumble and TeamSpeak 6 backends.

Python keeps all AI logic (Brain/Ear/Voice/AudioManager/Wakeword/handlers).
Backends only differ in transport:

- MumbleBackend: pymumble voice + text (default, USE_TEAMSPEAK=false).
- TeamspeakBackend: SSH ServerQuery :10022 for text/presence/move +
  Node/Go bridge sidecar for 48 kHz mono s16le PCM voice (USE_TEAMSPEAK=true).

PCM contract (both directions): 48 kHz, mono, signed 16-bit little-endian
bytes. This keeps AudioManager, UserVoiceStream, Ear.transcribe and
Voice.generate_pcm unchanged across backends.
"""
from abc import ABC, abstractmethod


class VoiceBackend(ABC):
    """Abstract voice+chat backend."""

    backend_name = "base"

    def __init__(self, bot):
        self.bot = bot

    # -- lifecycle -----------------------------------------------------
    @abstractmethod
    def connect(self):
        """Establish connection and register callbacks. May raise."""

    @abstractmethod
    def disconnect(self):
        """Close connection, stop threads/processes. Must not raise."""

    @abstractmethod
    def is_alive(self):
        """Return True while connected and usable."""

    # -- chat / channel ------------------------------------------------
    @abstractmethod
    def move_to_channel(self, name):
        """Join/move to a channel by name."""

    @abstractmethod
    def send_chat(self, text, target=None):
        """Send a text/chat message to the current channel (or target)."""

    # -- audio ----------------------------------------------------------
    @abstractmethod
    def play_pcm(self, pcm_bytes):
        """Queue 48k mono s16le PCM for playback."""

    @abstractmethod
    def clear_audio_buffer(self):
        """Drop any queued outbound audio (used by stop_speaking)."""

    # -- presence -------------------------------------------------------
    @abstractmethod
    def list_users(self):
        """Return [{name, id, channel}] for status / hourly reports."""

    @property
    @abstractmethod
    def my_channel_id(self):
        """Channel id (or name) the bot currently sits in, or None."""

    # -- optional hooks (default no-op) --------------------------------
    def set_bandwidth(self, bandwidth):
        """Mumble-only. No-op on TeamSpeak (kept for compat)."""

    @property
    def voice_bridge_status(self):
        """'Connected' / 'Down' / 'N/A'. Only TeamspeakBackend overrides."""
        return "N/A"
