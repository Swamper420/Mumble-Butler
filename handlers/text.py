import re
import config


class TextHandler:
    def __init__(self, bot):
        self.bot = bot

    # -- sender resolution (Mumble + TeamSpeak) ---------------------------
    def _resolve_sender(self, message):
        """Resolve (sender_name, text) from any supported event shape.

        Supports:
        - pymumble object with .actor (session id) + .message
        - TeamSpeak dict {invokername, msg} / raw "notifytextmessage ..." str
        - Direct (sender, text) tuple / generic dict
        - Legacy shim where .actor is already a name string
        Returns (sender_name, text) or (None, None) when ignored/unknown.
        """
        # Fast path: dict / str / tuple via shared normalizer (no bot filter
        # duplication — but we re-apply bot-aware filtering below).
        if isinstance(message, (dict, str, tuple, list)):
            try:
                from backends.teamspeak_backend import normalize_text_event
                normalized = normalize_text_event(message, bot=self.bot)
                if normalized:
                    return normalized
                # Fall through to legacy handling for pymumble-shaped dicts
            except Exception:
                pass

        actor = getattr(message, "actor", None)
        text = getattr(message, "message", getattr(message, "msg", None))
        if actor is None or text is None:
            return (None, None)

        # Legacy TS shim: actor already a display name
        if isinstance(actor, str):
            sender_name = actor
            if sender_name in (getattr(config, "IGNORED_USERS", []) or []):
                return (None, None)
            own = {getattr(config, "BOT_USERNAME", ""), getattr(config, "TS6_NICKNAME", "")}
            if sender_name in own:
                return (None, None)
            if not str(text).strip():
                return (None, None)
            return (sender_name, str(text))

        # pymumble path: actor is a session id
        sender_id = actor
        sender_name = None
        users = getattr(getattr(self.bot, "mumble", None), "users", None)
        try:
            if users is not None:
                # users may be a dict, a MagicMock wrapping a dict, or pymumble's
                # user container. Be tolerant (tests inject plain dicts).
                contains = False
                try:
                    contains = sender_id in users
                except Exception:
                    contains = False
                if contains:
                    try:
                        sender = users[sender_id] if hasattr(users, "__getitem__") else users.get(sender_id)
                    except Exception:
                        sender = None
                    if isinstance(sender, dict):
                        sender_name = sender.get("name")
                    elif sender is not None:
                        sender_name = getattr(sender, "name", None)
                else:
                    # Unknown session — still try backend list before dropping
                    sender_name = None
                try:
                    myself_session = getattr(users, "myself_session", None)
                    if sender_id == myself_session:
                        return (None, None)
                except Exception:
                    pass
        except Exception:
            pass

        # Fall back to backend user list (TS6 + MumbleBackend)
        if sender_name is None:
            backend = getattr(self.bot, "backend", None)
            if backend is not None:
                try:
                    for u in backend.list_users() or []:
                        if u.get("id") == sender_id:
                            sender_name = u.get("name")
                            break
                except Exception:
                    pass

        if sender_name is None:
            # No mumble alias and no backend hit: if users container is
            # missing entirely (pure mock bot), treat unknown numeric actors
            # as unresolvable; otherwise drop.
            return (None, None)

        if sender_name in (getattr(config, "IGNORED_USERS", []) or []):
            return (None, None)

        if not str(text).strip():
            return (None, None)
        return (sender_name, str(text))

    def handle(self, message):
        """Legacy entry point (pymumble callback). Also accepts TS shapes."""
        sender_name, text = self._resolve_sender(message)
        if not sender_name or text is None:
            return
        self.handle_text(sender_name, text)

    def handle_text(self, sender_name, text):
        """Shared core: route a (sender_name, text) pair to a command.

        Used by both Mumble (via handle()) and TeamSpeak query
        (notifytextmessage -> normalize -> handle_text).
        """
        if not sender_name or text is None:
            return
        sender_name = str(sender_name)
        text = str(text).strip()
        if not text:
            return
        if sender_name in (getattr(config, "IGNORED_USERS", []) or []):
            return

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
            available_voices = self.bot.voice.get_available_voices()

            if not arg:
                voices_list = ", ".join(available_voices) if available_voices else "None returned from TTS API"
                self.bot.send_chat(f"Available voices: {voices_list}")
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
                    # Allow setting custom voice string even if not in list
                    self.bot.voice.current_voice_id = arg
                    self.bot.send_chat(f"Voice changed to: {arg}")

        elif cmd == config.TEXT_TRIGGERS['SAY']:
            if arg:
                if len(arg) > 1000:
                    self.bot.send_chat("<b>Error:</b> Text-to-speech length is limited to 1000 characters.")
                else:
                    self.bot.say_async(arg, user=sender_name)

        elif cmd == config.TEXT_TRIGGERS['SAYSAVE']:
            if arg:
                if len(arg) > 1000:
                    self.bot.send_chat("<b>Error:</b> Text-to-speech length is limited to 1000 characters.")
                else:
                    self.bot.saysave_async(arg, user=sender_name)
            else:
                self.bot.send_chat("<b>Usage:</b> ?saysave &lt;text&gt;")

        elif cmd == config.TEXT_TRIGGERS['REMIND']:
            match = re.search(
                r"^(?:in\s+)?(\d+)\s+(second|minute|hour)s?(?:\s+(?:about|to))?\s+(.+)",
                arg.strip(),
                re.IGNORECASE
            )
            if match:
                amount = int(match.group(1))
                unit = match.group(2).lower()
                message = match.group(3).strip()
                
                unit_seconds = {
                    "second": 1,
                    "minute": 60,
                    "hour": 3600,
                }
                seconds = amount * unit_seconds[unit]
                normalized_unit = f"{unit}s" if amount != 1 else unit
                time_text = f"{amount} {normalized_unit}"
                
                self.bot.schedule_reminder(seconds, message)
                self.bot.send_chat(f"Reminder scheduled: I will remind you in {time_text} about {message}.")
            else:
                self.bot.send_chat("<b>Usage:</b> ?remind [in] &lt;amount&gt; &lt;second/minute/hour&gt;s [about] &lt;message&gt;<br/><i>Example: ?remind in 10 minutes about standup</i>")

        elif cmd == config.TEXT_TRIGGERS['RECOMMEND']:
            try:
                song, vibe = self.bot.brain.recommend_song(
                    arg or "random music",
                    chat_context=self.bot.recent_transcripts,
                    return_meta=True
                )
            except Exception as e:
                self.bot.send_chat(f"<b>Recommendation error:</b> {e}")
                return
            if song:
                msg = f"🎵 <b>Queued:</b> {song}"
                if vibe:
                    msg += f"<br/><i>Vibe: {vibe}</i>"
                self.bot.send_chat(msg)
                self.bot.play(song)
            else:
                self.bot.send_chat(
                    "<b>No recommendation found.</b> Try e.g. "
                    "<i>?recommend chill synthwave</i> or <i>?recommend Nightwish</i>."
                )

        elif cmd in ("?another", "?more", "?next"):
            # QoL: fresh pick excluding what's already in history (which
            # includes the last recommendation, since it was just added).
            try:
                song, vibe = self.bot.brain.recommend_song(
                    arg or "something else, different artist",
                    chat_context=self.bot.recent_transcripts,
                    return_meta=True
                )
            except Exception as e:
                self.bot.send_chat(f"<b>Recommendation error:</b> {e}")
                return
            if song:
                msg = f"🎵 <b>Queued (another):</b> {song}"
                if vibe:
                    msg += f"<br/><i>Vibe: {vibe}</i>"
                self.bot.send_chat(msg)
                self.bot.play(song)
            else:
                self.bot.send_chat("<b>No fresh recommendation found.</b> Try ?history to see recent picks.")

        elif cmd in ("?history", "?recent"):
            try:
                recent = self.bot.brain.recommender.history_summary(5)
            except Exception:
                recent = []
            if recent:
                items = "<br/>".join(f"{i+1}. {t}" for i, t in enumerate(recent))
                self.bot.send_chat(f"🎵 <b>Recent picks:</b><br/>{items}")
            else:
                self.bot.send_chat("🎵 No picks yet. Try <i>?recommend chill</i>.")

        elif cmd in ("?dislike", "?nope", "?bad"):
            # QoL: drop last pick, skip it, and recommend a replacement.
            removed = None
            try:
                removed = self.bot.brain.recommender.remove_last()
            except Exception:
                pass
            try:
                self.bot.skip()
            except Exception:
                pass
            if removed:
                self.bot.send_chat(f"👎 Skipped <i>{removed}</i> — won't repeat it soon.")
            try:
                song, vibe = self.bot.brain.recommend_song(
                    arg or "something else, different artist",
                    chat_context=self.bot.recent_transcripts,
                    return_meta=True
                )
            except Exception as e:
                self.bot.send_chat(f"<b>Recommendation error:</b> {e}")
                return
            if song:
                msg = f"🎵 <b>Queued instead:</b> {song}"
                if vibe:
                    msg += f"<br/><i>Vibe: {vibe}</i>"
                self.bot.send_chat(msg)
                self.bot.play(song)

        elif cmd == config.TEXT_TRIGGERS['SEARCH']:
            if arg:
                self.bot.send_chat(f"Haetaan verkosta: <i>{arg}</i>...")
                results = self.bot.brain.searcher.search(arg)
                search_ctx = self.bot.brain.searcher.format_search_context(arg, results)
                if results:
                    summary_prompt = f"Tiivistä seuraavat hakutulokset hakusanalle '{arg}' suomeksi:\n\n{search_ctx}"
                    self.bot.say_stream(summary_prompt, user=sender_name)
                else:
                    self.bot.send_chat(f"Hakutuloksia ei löytynyt hakusanalle '{arg}'.")
            else:
                self.bot.send_chat("<b>Käyttö:</b> ?search &lt;hakusana&gt;<br/><i>Esimerkki: ?search sää Helsingissä</i>")

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
