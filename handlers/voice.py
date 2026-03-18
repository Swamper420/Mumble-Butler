import re
import config


class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        # Pre-compile the activation pattern for efficiency
        sorted_keywords = sorted(config.ACTIVATION_KEYWORDS, key=len, reverse=True)
        self.activation_pattern = re.compile(
            r"^(" + "|".join(re.escape(k.lower()) for k in sorted_keywords) + r")\b"
        )

    def handle(self, user, text):
        """
        Returns True if a command was executed, False otherwise.
        """
        clean_text = re.sub(r'[^\w\s]', '', text).lower().strip()

        # 1. Check for Activation Keyword
        match = self.activation_pattern.search(clean_text)
        if not match:
            return False

        # Remove the trigger word to get the actual command content
        content = re.sub(self.activation_pattern, "", clean_text, count=1).strip()

        # 2. Check for shut-up keyword before anything else
        shutup_keywords = getattr(config, 'SHUTUP_KEYWORDS', [])
        if any(kw in content for kw in shutup_keywords):
            self.bot.listening_enabled = False
            self.bot.say_async("Fine, I'll be quiet.")
            return True

        # Play chime if configured
        if self.bot.chime_pcm and self.bot.mumble and self.bot.mumble.sound_output:
            self.bot.mumble.sound_output.add_sound(self.bot.chime_pcm)

        # 3. Process Logic
        handled = self._match_command(content)

        if not handled:
            # If no command matched, let the LLM answer
            response = self.bot.brain.generate_response(f"User {user} says: {content}")
            self.bot.say_async(response)

        return True

    def _match_command(self, content):
        """Matches content against config triggers."""

        # 1. Forget
        if any(w in content for w in config.VOICE_TRIGGERS['FORGET']):
            self.bot.brain.reset_memory()
            self.bot.say_async("Memory wiped.")
            return True

        # 2. Volume
        if any(w in content for w in config.VOICE_TRIGGERS['VOLUME']):
            m = re.search(r"(\d+)", content)
            if m:
                self.bot.set_volume(int(m.group(1)))
            return True

        # 3. Mode
        if any(w in content for w in config.VOICE_TRIGGERS['MODE']):
            modes = ["one-shot", "one shot", "oneshot", "autoplay", "repeat", "random"]
            for m in modes:
                if m in content:
                    target = "one-shot" if m in ["oneshot", "one shot"] else m
                    self.bot.set_mode(target)
                    return True
            self.bot.say_async("Available modes are: one-shot, autoplay, repeat, and random.")
            return True

        # 4. Recommend
        if any(w in content for w in config.VOICE_TRIGGERS['RECOMMEND']):
            desc = content
            for t in config.VOICE_TRIGGERS['RECOMMEND']:
                desc = desc.replace(t, "")
            song = self.bot.brain.recommend_song(desc.strip() or "random music")
            if song:
                self.bot.say_async(f"Queued {song}")
                self.bot.play(song)
            return True

        # 5. Play / Queue (Specific)
        if any(w in content for w in config.VOICE_TRIGGERS['PLAY_SPECIFIC']):
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_SPECIFIC'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                self.bot.play(q.group(1))
            return True

        # 6. Play (Generic Music / "music")
        if any(w in content for w in config.VOICE_TRIGGERS['PLAY_MUSIC']):
            rec = self.bot.brain.recommend_song("random music")
            if rec:
                self.bot.say_async(f"Queued {rec}")
                self.bot.play(rec)
            return True

        # 7. Resume (if paused)
        if any(w in content for w in config.VOICE_TRIGGERS.get('RESUME', [])):
            self.bot.resume_music()
            return True

        # 8. Stop (full halt)
        if any(w in content for w in config.VOICE_TRIGGERS['STOP']):
            self.bot.stop_music()
            return True

        # 9. Skip / Next
        if any(w in content for w in config.VOICE_TRIGGERS['SKIP']):
            self.bot.skip()
            return True

        # 10. File
        if any(w in content for w in config.VOICE_TRIGGERS['PLAY_FILE']):
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_FILE'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                self.bot.play_file(q.group(1))
            return True

        # 11. Repeat
        if any(w in content for w in config.VOICE_TRIGGERS['REPEAT']):
            m = re.search(r"(\d+)", content)
            count = int(m.group(1)) if m else 1
            self.bot.repeat_music(count)
            return True

        return False
