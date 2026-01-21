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

        # Play chime if configured
        if self.bot.chime_pcm and self.bot.mumble and self.bot.mumble.sound_output:
            self.bot.mumble.sound_output.add_sound(self.bot.chime_pcm)

        # 2. Process Logic
        cmd_out = self._match_command(content)

        if cmd_out:
            self.bot.send_chat(cmd_out)
        else:
            # If no command matched, talk to the LLM
            response = self.bot.brain.generate_response(f"User {user} says: {content}")
            self.bot.say_async(response)

        return True

    def _match_command(self, content):
        """Matches content against config triggers."""

        # 1. Forget
        if any(w in content for w in config.VOICE_TRIGGERS['FORGET']):
            self.bot.brain.reset_memory()
            self.bot.say_async("Memory wiped.")
            return None # Action handled locally, no chat command needed

        # 2. Volume
        if any(w in content for w in config.VOICE_TRIGGERS['VOLUME']):
            m = re.search(r"(\d+)", content)
            if m:
                return f"{config.MUMBLE_COMMANDS['VOLUME']} {m.group(1)}"

        # 3. Mode
        elif any(w in content for w in config.VOICE_TRIGGERS['MODE']):
            modes = ["one-shot", "one shot", "oneshot", "autoplay", "repeat", "random"]
            for m in modes:
                if m in content:
                    target = "one-shot" if m in ["oneshot", "one shot"] else m
                    self.bot.say_async(f"Setting mode to {target}")
                    return f"{config.MUMBLE_COMMANDS['MODE']} {target}"
            self.bot.say_async("Available modes are: one-shot, autoplay, repeat, and random.")
            return None

        # 4. Recommend
        elif any(w in content for w in config.VOICE_TRIGGERS['RECOMMEND']):
            desc = content
            for t in config.VOICE_TRIGGERS['RECOMMEND']:
                desc = desc.replace(t, "")
            song = self.bot.brain.recommend_song(desc.strip() or "random music")
            if song:
                self.bot.say_async(f"Queued {song}")
                return f"{config.MUMBLE_COMMANDS['PLAY_YOUTUBE']} {song}"

        # 5. Play / Queue (Specific)
        elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_SPECIFIC']):
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_SPECIFIC'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                return f"{config.MUMBLE_COMMANDS['PLAY_YOUTUBE']} {q.group(1)}"

        # 6. Play (Generic Music)
        elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_MUSIC']):
            return config.MUMBLE_COMMANDS['PLAY_GENERIC']

        # 7. Stop / Pause
        elif any(w in content for w in config.VOICE_TRIGGERS['STOP']):
            return config.MUMBLE_COMMANDS['PAUSE']

        # 8. Skip / Next
        elif any(w in content for w in config.VOICE_TRIGGERS['SKIP']):
            return config.MUMBLE_COMMANDS['SKIP']

        # 9. File
        elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_FILE']):
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_FILE'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                return f"{config.MUMBLE_COMMANDS['FILE']} {q.group(1)}"

        # 10. Repeat
        elif any(w in content for w in config.VOICE_TRIGGERS['REPEAT']):
            m = re.search(r"(\d+)", content)
            count = m.group(1) if m else "1"
            return f"{config.MUMBLE_COMMANDS['REPEAT']} {count}"

        return None
