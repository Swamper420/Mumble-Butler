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
            cmds = ", ".join(config.TEXT_TRIGGERS.values())
            self.bot.send_chat(f"Commands: {cmds}, ?voice [name]")

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
            if arg.lower() in config.AVAILABLE_VOICES:
                self.bot.voice.current_voice_id = config.AVAILABLE_VOICES[arg.lower()]
                self.bot.send_chat(f"Voice changed to: {arg}")
            else:
                voices_list = ", ".join(config.AVAILABLE_VOICES.keys())
                self.bot.send_chat(f"Available voices: {voices_list}")

        elif cmd == config.TEXT_TRIGGERS['SAY']:
            if arg:
                self.bot.say_async(arg)

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
