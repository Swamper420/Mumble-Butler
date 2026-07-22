import re
import config
try:
    from rapidfuzz import fuzz as _fuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    _FUZZY_AVAILABLE = False


class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        # Collect base names of custom models and builtins from wakeword detector
        keywords = list(config.ACTIVATION_KEYWORDS)
        if hasattr(bot, 'wakeword_detector') and bot.wakeword_detector.enabled and bot.wakeword_detector.model:
            for k in bot.wakeword_detector.model.models.keys():
                clean_name = k.lower().replace("_", " ").strip()
                if clean_name not in keywords:
                    keywords.append(clean_name)
                if "_" in k:
                    collapsed_name = k.lower().replace("_", "").strip()
                    if collapsed_name not in keywords:
                        keywords.append(collapsed_name)

        self.sorted_keywords = sorted(keywords, key=len, reverse=True)
        # Pre-compile the exact activation pattern for fast-path matching
        self.activation_pattern = re.compile(
            r"^(" + "|".join(re.escape(k.lower()) for k in self.sorted_keywords) + r")\b"
        )

    def _detect_activation(self, clean_text):
        """
        Returns the command content (text after the wake word) if an activation
        keyword is found, or None if not.

        Detection order:
        1. Exact prefix regex — fastest, zero false positives.
        2. Fuzzy word scan   — catches STT mistranscriptions (needs rapidfuzz).
        """
        # 1. Exact match
        match = self.activation_pattern.search(clean_text)
        if match:
            return re.sub(self.activation_pattern, "", clean_text, count=1).strip()

        # 2. Fuzzy fallback
        if _FUZZY_AVAILABLE:
            words = clean_text.split()
            for i, word in enumerate(words):
                if any(_fuzz.ratio(word, kw) >= 82 for kw in self.sorted_keywords):
                    return " ".join(words[i + 1:]).strip()

        return None

    def handle(self, user, text):
        """
        Returns True if a command was executed, False otherwise.
        """
        clean_text = re.sub(r'[^\w\s]', '', text).lower().strip()

        # 1. Check for Activation Keyword (exact, then fuzzy)
        content = self._detect_activation(clean_text)
        if content is None:
            return False

        # 2. Check for shut-up keyword before anything else
        shutup_keywords = getattr(config, 'SHUTUP_KEYWORDS', [])
        if any(kw in content for kw in shutup_keywords):
            self.bot.stop_speaking()
            return True

        # Play ack sound if configured (wakeword or chime)
        self.bot.play_ack_sound()

        # 3. Process Logic
        handled = self._match_command(user, content)

        if not handled:
            # Check if search keyword is present
            if any(w in content for w in config.VOICE_TRIGGERS.get('SEARCH', [])):
                self.bot.play_action_confirmation("SEARCH")
            else:
                self.bot.play_action_confirmation("THINK")
            # If no command matched, let the LLM answer
            self.bot.say_stream(f"User {user} says: {content}", user=user)

        return True

    def _match_command(self, user, content):
        """Matches content against config triggers."""

        if any(w in content for w in config.VOICE_TRIGGERS['FORGET']):
            self.bot.play_action_confirmation("MEMORY")
            self.bot.brain.reset_memory()
            self.bot.say_async("Memory wiped.", user=user)
            return True

        # 2. Volume
        if any(w in content for w in config.VOICE_TRIGGERS['VOLUME']):
            self.bot.play_action_confirmation("VOLUME")
            m = re.search(r"(\d+)", content)
            if m:
                self.bot.set_volume(int(m.group(1)))
            return True

        # 3. Mode
        if any(w in content for w in config.VOICE_TRIGGERS['MODE']):
            self.bot.play_action_confirmation("MODE")
            modes = ["one-shot", "one shot", "oneshot", "autoplay", "repeat", "random"]
            for m in modes:
                if m in content:
                    target = "one-shot" if m in ["oneshot", "one shot"] else m
                    self.bot.set_mode(target)
                    return True
            self.bot.say_async("Available modes are: one-shot, autoplay, repeat, and random.", user=user)
            return True

        # 4. Recommend
        if any(w in content for w in config.VOICE_TRIGGERS['RECOMMEND']):
            self.bot.play_action_confirmation("MUSIC")
            desc = content
            for t in config.VOICE_TRIGGERS['RECOMMEND']:
                desc = desc.replace(t, "")
            song, vibe = self.bot.brain.recommend_song(
                desc.strip() or "random music",
                chat_context=self.bot.recent_transcripts,
                return_meta=True
            )
            if song:
                announcement = f"Queued {song}. {vibe}" if vibe else f"Queued {song}"
                self.bot.say_async(announcement, user=user)
                self.bot.play(song)
            return True

        # 5. Play / Queue (Specific)
        if any(w in content for w in config.VOICE_TRIGGERS['PLAY_SPECIFIC']):
            self.bot.play_action_confirmation("MUSIC")
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_SPECIFIC'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                self.bot.play(q.group(1))
            return True

        # 6. Play (Generic Music / "music")
        if any(w in content for w in config.VOICE_TRIGGERS['PLAY_MUSIC']):
            self.bot.play_action_confirmation("MUSIC")
            rec, vibe = self.bot.brain.recommend_song(
                "random music",
                chat_context=self.bot.recent_transcripts,
                return_meta=True
            )
            if rec:
                announcement = f"Queued {rec}. {vibe}" if vibe else f"Queued {rec}"
                self.bot.say_async(announcement, user=user)
                self.bot.play(rec)
            return True

        # 7. Resume (if paused)
        if any(w in content for w in config.VOICE_TRIGGERS.get('RESUME', [])):
            self.bot.play_action_confirmation("RESUME")
            self.bot.resume_music()
            return True

        # 8. Stop (full halt)
        if any(w in content for w in config.VOICE_TRIGGERS['STOP']):
            self.bot.play_action_confirmation("STOP")
            self.bot.stop_music()
            return True

        # 9. Skip / Next
        if any(w in content for w in config.VOICE_TRIGGERS['SKIP']):
            self.bot.play_action_confirmation("SKIP")
            self.bot.skip()
            return True

        # 10. File
        if any(w in content for w in config.VOICE_TRIGGERS['PLAY_FILE']):
            self.bot.play_action_confirmation("FILE")
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_FILE'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                self.bot.play_file(q.group(1))
            return True

        # 11. Repeat
        if any(w in content for w in config.VOICE_TRIGGERS['REPEAT']):
            self.bot.play_action_confirmation("REPEAT")
            m = re.search(r"(\d+)", content)
            count = int(m.group(1)) if m else 1
            self.bot.repeat_music(count)
            return True

        # 12. Remind
        if any(w in content for w in config.VOICE_TRIGGERS.get('REMIND', [])):
            self.bot.play_action_confirmation("REMIND")
            reminder = self._parse_reminder(content)
            if reminder:
                seconds, time_text, message = reminder
                self.bot.schedule_reminder(seconds, message)
                self.bot.say_async(f"I will remind you in {time_text}.", user=user)
            else:
                self.bot.say_async("Try saying remind me in 10 minutes about something.", user=user)
            return True

        # 13. Status
        if any(w in content for w in config.VOICE_TRIGGERS.get('STATUS', [])):
            self.bot.play_action_confirmation("STATUS")
            status = self.bot.get_status()
            summary = f"I am connected with an uptime of {status['Uptime']}. The LLM is {status['LLM']}. Listening is {status['Listening']}."
            self.bot.say_async(summary, user=user)
            return True

        # 14. Ping
        if any(w in content for w in config.VOICE_TRIGGERS.get('PING', [])):
            self.bot.play_action_confirmation("PING")
            self.bot.say_async("Pong! I am here.", user=user)
            return True

        return False

    def _parse_reminder(self, content):
        match = re.search(
            r"\bremind(?: me)? in (\d+)\s+(second|minute|hour)s?\b\s+(?:(?:about|to)\s+)?(.+)",
            content,
        )
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2)
        message = (match.group(3) or "").strip()
        if not message:
            return None
        unit_seconds = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
        }
        normalized_unit = f"{unit}s" if amount != 1 else unit

        return amount * unit_seconds[unit], f"{amount} {normalized_unit}", message
