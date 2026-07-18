import config


class TextHandler:
    def __init__(self, bot):
        self.bot = bot

    def handle(self, message):
        """Parses and executes text commands."""
        sender_id = message.actor

        # Validation checks
        if sender_id not in self.bot.mumble.users:
            return

        sender = self.bot.mumble.users[sender_id]
        if sender_id == self.bot.mumble.users.myself_session:
            return

        if sender['name'] in config.IGNORED_USERS:
            return

        text = message.message.strip()
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        # --- Command Routing ---

        if cmd == config.TEXT_TRIGGERS['HELP']:
            triggers = list(config.TEXT_TRIGGERS.values())
            # Add dynamic voice command example
            triggers.append("?voice [name]")
            triggers.append("?play [query]")
            triggers.append("?volume [0-100]")
            triggers.append("?ping")
            triggers.append("?clear")
            triggers.append("?prompt [text]")
            triggers.append("?undo")

            help_text = "<b>Available Commands:</b><br/>" + ", ".join(triggers)
            help_text += "<br/><i>Use ?status to check system health.</i>"
            self.bot.send_chat(help_text)

        elif cmd == config.TEXT_TRIGGERS['STATUS']:
            status = self.bot.get_status()
            status_text = "<b>System Status:</b><br/>"
            for key, val in status.items():
                color = "green" if val in ["Connected", "Online", "Ready", "ON"] else "red"
                status_text += f"{key}: <span style='color:{color}'>{val}</span><br/>"
            self.bot.send_chat(status_text)

        elif cmd == config.TEXT_TRIGGERS['LISTEN']:
            self.bot.listening_enabled = not self.bot.listening_enabled
            status = "ON" if self.bot.listening_enabled else "OFF"
            self.bot.send_chat(f"Listening: {status}")

        elif cmd == config.TEXT_TRIGGERS['FORGET']:
            self.bot.brain.reset_memory()
            self.bot.send_chat("Memory wiped.")

        elif cmd == config.TEXT_TRIGGERS['MEMORY']:
            new_state = self.bot.brain.toggle_memory()
            state_str = "ENABLED" if new_state else "DISABLED"
            self.bot.send_chat(f"Context Memory: {state_str}")

        elif cmd == config.TEXT_TRIGGERS['VOICE']:
            if getattr(self.bot.voice, "engine", "kokoro") == "chatterbox-turbo":
                import glob
                voice_dir = getattr(config, "CHATTERBOX_VOICE_DIR", "data/voices")
                os.makedirs(voice_dir, exist_ok=True)
                wav_files = glob.glob(os.path.join(voice_dir, "*.wav"))
                available_voices = [os.path.splitext(os.path.basename(f))[0] for f in wav_files]

                if not arg:
                    voices_list = ", ".join(available_voices) if available_voices else "None (drop .wav files in data/voices/)"
                    self.bot.send_chat(f"Available Chatterbox voices: {voices_list}")
                else:
                    clean_arg = arg.lower()
                    matched = None
                    for v in available_voices:
                        if v.lower() == clean_arg:
                            matched = v
                            break
                    if matched:
                        self.bot.voice.current_voice_id = matched
                        self.bot.send_chat(f"Voice changed to: {matched}")
                    else:
                        self.bot.send_chat(f"Voice '{arg}' not found. Place a '{arg}.wav' file in {voice_dir} to clone it.")
            else:
                if arg.lower() in config.AVAILABLE_VOICES:
                    self.bot.voice.current_voice_id = config.AVAILABLE_VOICES[arg.lower()]
                    self.bot.send_chat(f"Voice changed to: {arg}")
                else:
                    voices_list = ", ".join(config.AVAILABLE_VOICES.keys())
                    self.bot.send_chat(f"Available Kokoro voices: {voices_list}")

        elif cmd == config.TEXT_TRIGGERS['SAY']:
            if arg:
                self.bot.say_async(arg, user=sender['name'])

        elif cmd == config.TEXT_TRIGGERS['RECOMMEND']:
            song = self.bot.brain.recommend_song(arg or "random music", chat_context=self.bot.recent_transcripts)
            if song:
                self.bot.send_chat(f"Queued: {song}")
                self.bot.play(song)

        elif cmd == "?ping":
            self.bot.send_chat("Pong!")

        elif cmd == "?undo":
            if self.bot.brain.undo_last_memory():
                self.bot.send_chat("Last interaction forgotten.")
            else:
                self.bot.send_chat("No memory to undo.")

        elif cmd == "?prompt":
            if arg:
                if arg.lower() == "reset":
                    self.bot.brain.dynamic_prompt = None
                    self.bot.send_chat("System prompt reset to default.")
                else:
                    self.bot.brain.dynamic_prompt = arg
                    self.bot.send_chat("System prompt updated dynamically.")
            else:
                current_prompt = self.bot.brain.dynamic_prompt or "Default"
                self.bot.send_chat(f"Current dynamic prompt: {current_prompt}. Use '?prompt reset' to restore default.")

        # --- music commands forwarded to botamusique ---
        elif cmd == "?play":
            if arg:
                self.bot.play(arg)
        elif cmd == "?now":
            self.bot.request_now_playing()
        elif cmd == "?queue":
            self.bot.request_queue()
        elif cmd == "?skip":
            self.bot.skip()
        elif cmd == "?clear":
            self.bot.clear_queue()
        elif cmd == "?stop":
            self.bot.stop_music()
        elif cmd == "?pause":
            self.bot.pause_music()
        elif cmd == "?resume":
            self.bot.resume_music()
        elif cmd == "?volume":
            try:
                level = int(arg)
                self.bot.set_volume(level)
            except ValueError:
                self.bot.send_chat("Usage: ?volume <0-100>")
        elif cmd == "?repeat":
            try:
                count = int(arg)
                self.bot.repeat_music(count)
            except ValueError:
                self.bot.send_chat("Usage: ?repeat <times>")
        elif cmd == "?mode":
            self.bot.set_mode(arg.lower())
