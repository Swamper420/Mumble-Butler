import re
import config
import random
from modules.jellyfin import JellyfinClient

class VoiceHandler:
    def __init__(self, bot):
        self.bot = bot
        sorted_keywords = sorted(config.ACTIVATION_KEYWORDS, key=len, reverse=True)
        self.activation_pattern = re.compile(
            r"^(" + "|".join(re.escape(k.lower()) for k in sorted_keywords) + r")\b"
        )
        self.jellyfin = JellyfinClient()

    def handle(self, user, text):
        clean_text = re.sub(r'[^\w\s]', '', text).lower().strip()

        match = self.activation_pattern.search(clean_text)
        if not match:
            return False

        content = re.sub(self.activation_pattern, "", clean_text, count=1).strip()

        if self.bot.chime_pcm and self.bot.mumble and self.bot.mumble.sound_output:
            self.bot.mumble.sound_output.add_sound(self.bot.chime_pcm)

        # Check for commands
        cmd_out = self._match_command(content)

        # If cmd_out is explicitly True, it means "Handled locally, do nothing else"
        if cmd_out is True:
            return True

        # If cmd_out is a string, send it to Mumble chat
        elif cmd_out:
            self.bot.send_chat(cmd_out)
            return True

        # If None, fallback to LLM
        else:
            response = self.bot.brain.generate_response(f"User {user} says: {content}")
            self.bot.say_async(response)
            return True

    def _match_command(self, content):
            """Matches content against config triggers."""
            # --- SAFETY CHECK ---
            if 'REMIND' not in config.VOICE_TRIGGERS:
                print("ERROR: 'REMIND' key missing from config.py!")
                return None

            # 11. Reminders
            if any(w in content for w in config.VOICE_TRIGGERS['REMIND']):
                # regex: Matches number, then unit.
                # Then OPTIONALLY matches space + (about/to) + message
                regex = r"(\d+)\s*(seconds?|minutes?|mins?|hours?)(?:\s+(?:about|to)?\s*(.*))?"
                match = re.search(regex, content)

                if match:
                    amount = int(match.group(1))
                    unit = match.group(2)
                    # group(3) might be None if no message was given
                    message = match.group(3)

                    # Convert to seconds
                    if "minute" in unit or "min" in unit:
                        seconds = amount * 60
                    elif "hour" in unit:
                        seconds = amount * 3600
                    else:
                        seconds = amount

                    # Default message if None or empty
                    if not message or not message.strip():
                        message = "do the thing you asked about."
                    else:
                        message = message.strip()

                    # Schedule it
                    print(f"DEBUG: Scheduling reminder for {seconds}s: '{message}'")
                    self.bot.schedule_reminder(seconds, message)
                    self.bot.say_async(f"I will remind you in {amount} {unit}.")
                    return True
                else:
                    print(f"DEBUG: Remind keyword found but regex failed on: '{content}'")

            # ... (Rest of your existing commands: FORGET, VOLUME, MODE, etc.) ...

            # 3. Volume
            if any(w in content for w in config.VOICE_TRIGGERS['VOLUME']):
                m = re.search(r"(\d+)", content)
                if m:
                    return f"{config.MUMBLE_COMMANDS['VOLUME']} {m.group(1)}"

            # 4. Mode
            elif any(w in content for w in config.VOICE_TRIGGERS['MODE']):
                modes = ["one-shot", "one shot", "oneshot", "autoplay", "repeat", "random"]
                for m in modes:
                    if m in content:
                        target = "one-shot" if m in ["oneshot", "one shot"] else m
                        self.bot.say_async(f"Setting mode to {target}")
                        return f"{config.MUMBLE_COMMANDS['MODE']} {target}"
                self.bot.say_async("Available modes are: one-shot, autoplay, repeat, and random.")
                return True

    # 5. Recommend (Strict 50/50 Coin Flip)
            if any(w in content for w in config.VOICE_TRIGGERS['RECOMMEND']):
                # 1. Clean input
                user_request = content
                for t in config.VOICE_TRIGGERS['RECOMMEND']:
                    user_request = user_request.replace(t, "")
                user_request = user_request.strip()

                # 2. Fetch Seed
                title, artist = self.jellyfin.get_random_track_seed()

                # 3. The Coin Flip
                # We flip the coin FIRST.
                # True = Play Jellyfin file directly (Ignores user_request)
                # False = Use LLM (Uses user_request + Jellyfin seed)
                use_direct_jellyfin = False

                if title:
                    use_direct_jellyfin = random.choice([True, False])
                else:
                    # If Jellyfin fetch failed (None), we MUST use LLM fallback
                    print("DEBUG: Jellyfin seed fetch failed. Forcing LLM mode.")
                    use_direct_jellyfin = False

                # --- PATH A: DIRECT JELLYFIN (The "Shuffle" feature) ---
                if use_direct_jellyfin:
                    # Format: "Artist - Title" for the !yplay command
                    search_query = f"{artist} - {title}"

                    print(f"DEBUG: Recommend Mode: DIRECT JELLYFIN -> {search_query}")

                    # Explicitly state what is happening
                    self.bot.say_async(f"Queuing {title}")

                    # Use !yplay to leverage botamusique's search
                    return f"!yplay {search_query}"


                # --- PATH B: LLM INSPIRATION (The "Discovery" feature) ---
                else:
                    prompt = ""

                    if title:
                        if user_request:
                            # "Recommend metal" + Seed "Toxic" -> Metal inspired by Toxic
                            prompt = f"{user_request}, influenced by the song {title} by {artist}"
                        else:
                            # "Recommend" + Seed "Toxic" -> Songs like Toxic
                            prompt = f"songs similar to {title} by {artist}"
                    else:
                        # Fallback (Jellyfin down)
                        prompt = user_request if user_request else "random music"

                    print(f"DEBUG: Recommend Mode: LLM -> {prompt}")

                    # Generate recommendation
                    song = self.bot.brain.recommend_song(prompt)

                    if song:
                        self.bot.say_async(f"Queuing {song}")
                        return f"{config.MUMBLE_COMMANDS['PLAY_YOUTUBE']} {song}"
                    else:
                        # Handle the "does nothing" case if LLM fails
                        self.bot.say_async("I couldn't think of a song.")
                        return True

                return True

            # 6. Play / Queue (Specific)
            elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_SPECIFIC']):
                triggers = "|".join(config.VOICE_TRIGGERS['PLAY_SPECIFIC'])
                q = re.search(rf"(?:{triggers})\s+(.*)", content)
                if q:
                    return f"{config.MUMBLE_COMMANDS['PLAY_YOUTUBE']} {q.group(1)}"

            # 7. Play (Generic Music)
            elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_MUSIC']):
                return config.MUMBLE_COMMANDS['PLAY_GENERIC']

            # 8. Stop / Pause
            elif any(w in content for w in config.VOICE_TRIGGERS['STOP']):
                return config.MUMBLE_COMMANDS['PAUSE']

            # 9. Skip / Next
            elif any(w in content for w in config.VOICE_TRIGGERS['SKIP']):
                return config.MUMBLE_COMMANDS['SKIP']

            # 10. File
            elif any(w in content for w in config.VOICE_TRIGGERS['PLAY_FILE']):
                triggers = "|".join(config.VOICE_TRIGGERS['PLAY_FILE'])
                q = re.search(rf"(?:{triggers})\s+(.*)", content)
                if q:
                    return f"{config.MUMBLE_COMMANDS['FILE']} {q.group(1)}"

            # 11. Repeat
            elif any(w in content for w in config.VOICE_TRIGGERS['REPEAT']):
                m = re.search(r"(\d+)", content)
                count = m.group(1) if m else "1"
                return f"{config.MUMBLE_COMMANDS['REPEAT']} {count}"

            # 1. Forget (Placed last or check existing list order)
            if any(w in content for w in config.VOICE_TRIGGERS['FORGET']):
                self.bot.brain.reset_memory()
                self.bot.say_async("Memory wiped.")
                return True


            return None
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
            # fall back to a recommendation if no query provided
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

        # 9. File
        if any(w in content for w in config.VOICE_TRIGGERS['PLAY_FILE']):
            triggers = "|".join(config.VOICE_TRIGGERS['PLAY_FILE'])
            q = re.search(rf"(?:{triggers})\s+(.*)", content)
            if q:
                self.bot.play(q.group(1))
            return True

        # 10. Repeat
        if any(w in content for w in config.VOICE_TRIGGERS['REPEAT']):
            m = re.search(r"(\d+)", content)
            count = int(m.group(1)) if m else 1
            self.bot.repeat_music(count)
            return True

        return False
