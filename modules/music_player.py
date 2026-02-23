import os
import re
import threading
import time
import subprocess


try:
    import yt_dlp
except ImportError:  # pragma: no cover
    yt_dlp = None

from utils import adjust_volume_pcm
import config


class MusicPlayer:
    """Internal music playback engine that replaces botamusique.

    - maintains a queue of tracks
    - fetches audio URLs via yt-dlp (supports search queries)
    - streams audio through ffmpeg directly into the bot's Mumble output
    - exposes control methods for play, pause, skip, volume, repeat etc.
    """

    def __init__(self, bot):
        self.bot = bot
        self.queue = []                 # list of dicts with at least 'query'
        self.current = None             # item currently playing
        self.process = None             # ffmpeg subprocess for current track
        self.lock = threading.Lock()
        self.play_event = threading.Event()

        # state variables
        self.volume = 100               # percentage (0-100)
        self.pause_flag = False
        self.repeat_count = 0
        self.mode = "one-shot"         # one-shot, autoplay, repeat, random

        thread = threading.Thread(target=self._player_loop, daemon=True)
        thread.start()

    # public control methods ------------------------------------------------

    def queue_track(self, query: str):
        """Add a new query/url/path to the end of the queue."""
        item = {"query": query}
        with self.lock:
            self.queue.append(item)
            self.play_event.set()
        self.bot.send_chat(f"✅ Queued: {query}")
        return item

    def play_now(self, query: str):
        """Immediately stop current playback and play this query."""
        self.stop()
        with self.lock:
            self.queue.insert(0, {"query": query})
            self.play_event.set()
        self.bot.send_chat(f"▶️ Playing now: {query}")

    def skip(self):
        """Skip the currently playing track."""
        with self.lock:
            if self.process:
                try:
                    self.process.kill()
                except:  # pylint: disable=bare-except
                    pass
        self.bot.send_chat("⏭️ Skipped")

    def stop(self):
        """Cease playback and clear the queue."""
        with self.lock:
            self.queue.clear()
            if self.process:
                try:
                    self.process.kill()
                except:  # pylint: disable=bare-except
                    pass
        self.bot.send_chat("⏹️ Stopped playback")

    def set_volume(self, level: int):
        """Set playback volume (0-100)."""
        with self.lock:
            self.volume = max(0, min(100, level))
        self.bot.send_chat(f"🔊 Volume set to {self.volume}%")

    def pause(self):
        with self.lock:
            self.pause_flag = True
        self.bot.send_chat("⏸️ Paused")

    def resume(self):
        with self.lock:
            self.pause_flag = False
        self.bot.send_chat("▶️ Resumed")
        # make sure playback thread is awake
        self.play_event.set()

    def repeat(self, count: int):
        with self.lock:
            self.repeat_count = max(0, count)
        self.bot.send_chat(f"🔁 Will repeat current track {self.repeat_count} time(s)")

    def set_mode(self, mode: str):
        if mode not in ("one-shot", "autoplay", "repeat", "random"):
            self.bot.send_chat("⚠️ Unknown mode")
            return
        with self.lock:
            self.mode = mode
        self.bot.send_chat(f"🎚️ Mode set to {mode}")

    def now_playing(self):
        if self.current:
            return self.current.get("title", self.current.get("query"))
        return None

    def queue_list(self):
        with self.lock:
            return [item.get("title", item.get("query")) for item in self.queue]

    # internal helpers -------------------------------------------------------

    def _player_loop(self):
        while True:
            # wait until there is something to play
            self.play_event.wait()
            self.play_event.clear()

            next_item = None
            with self.lock:
                if self.queue:
                    next_item = self.queue.pop(0)

            if not next_item:
                continue

            self.current = next_item
            try:
                self._play_item(next_item)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"Playback error: {exc}")
            self.current = None

            # handle repeat logic
            with self.lock:
                if self.repeat_count > 0:
                    self.repeat_count -= 1
                    # requeue same track
                    self.queue.insert(0, next_item)
                    self.play_event.set()
                elif self.mode == "autoplay":
                    # ask brain for another recommendation
                    rec = self.bot.brain.recommend_song("random music")
                    if rec:
                        self.queue.append({"query": rec})
                        self.play_event.set()
                elif self.mode == "random" and self.queue:
                    import random

                    random.shuffle(self.queue)

    def _play_item(self, item: dict):
        # figure out a playable URL/file
        src = self._resolve_source(item["query"])
        if not src:
            return
        item["title"] = src.get("title", item["query"])
        self.bot.send_chat(f"🎶 Now playing: {item['title']}")

        ff_cmd = [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            src["url"],
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "1",
            "pipe:1",
        ]

        # spawn process
        with self.lock:
            self.process = subprocess.Popen(
                ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )

        try:
            while True:
                with self.lock:
                    if self.pause_flag:
                        time.sleep(0.1)
                        continue
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                with self.lock:
                    vol = self.volume / 100.0
                if vol != 1.0:
                    chunk = adjust_volume_pcm(chunk, vol)
                if self.bot.mumble and self.bot.mumble.sound_output:
                    try:
                        self.bot.mumble.sound_output.add_sound(chunk)
                    except:  # pylint: disable=bare-except
                        pass
        finally:
            with self.lock:
                if self.process:
                    try:
                        self.process.kill()
                    except:  # pylint: disable=bare-except
                        pass
                self.process = None

    def _resolve_source(self, query: str):
        # local file takes precedence
        if os.path.isfile(query):
            return {"url": query, "title": os.path.basename(query)}

        # otherwise use yt-dlp to resolve
        if yt_dlp is None:
            self.bot.send_chat("⚠️ yt-dlp not installed; cannot search online.")
            return None

        try:
            ydl_opts = {"format": "bestaudio/best", "quiet": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if re.match(r"https?://", query):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    if "entries" in info and info["entries"]:
                        info = info["entries"][0]
                # prefer webpage_url so ffmpeg can handle it directly
                url = info.get("webpage_url") or info.get("url")
                return {"url": url, "title": info.get("title", query)}
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Source resolution error: {exc}")
            self.bot.send_chat("⚠️ Could not retrieve audio for query.")
            return None
