import re
import config

try:
    from handlers.voice import (
        GENERIC_MUSIC_QUERIES,
        VAGUE_MUSIC_WORDS,
        GENRE_WORDS,
    )
except Exception:  # pragma: no cover - import fallback for odd runtimes
    GENERIC_MUSIC_QUERIES = frozenset({"music", "musiikkia"})
    VAGUE_MUSIC_WORDS = frozenset({"something", "jotain"})
    GENRE_WORDS = frozenset({"jazz"})


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
            triggers.append("?recommend [vibe] [count]")
            triggers.append("?surprise")
            triggers.append("?history")
            triggers.append("?dislike")
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
                    self.bot.say_async(arg, user=sender['name'])

        elif cmd == config.TEXT_TRIGGERS['SAYSAVE']:
            if arg:
                if len(arg) > 1000:
                    self.bot.send_chat("<b>Error:</b> Text-to-speech length is limited to 1000 characters.")
                else:
                    self.bot.saysave_async(arg, user=sender['name'])
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
            desc, count = self._parse_recommend_args(arg)
            tracks, vibe = self._recommend_tracks(desc or "random music", count)
            if tracks:
                self._announce_tracks(tracks, vibe, desc)
                for track in tracks:
                    self.bot.play(track)

        elif cmd == config.TEXT_TRIGGERS.get('SURPRISE', '?surprise'):
            tracks, vibe = self._recommend_tracks("random music", 1)
            if tracks:
                self._announce_tracks(tracks, vibe, "random music")
                for track in tracks:
                    self.bot.play(track)

        elif cmd == config.TEXT_TRIGGERS.get('HISTORY', '?history'):
            history = self._get_history(10)
            if history:
                lines = "<br/>".join(f"{i + 1}. {t}" for i, t in enumerate(history))
                self.bot.send_chat(f"🎵 <b>Recently played:</b><br/>{lines}")
            else:
                self.bot.send_chat("No recently played tracks yet.")

        elif cmd == config.TEXT_TRIGGERS.get('DISLIKE', '?dislike'):
            if self._dislike_last():
                self.bot.send_chat("👎 Noted — I'll avoid that one for a while. Skipping…")
                try:
                    self.bot.skip()
                except Exception:
                    pass
            else:
                self.bot.send_chat("Nothing to dislike right now.")

        elif cmd == config.TEXT_TRIGGERS['SEARCH']:
            if arg:
                self.bot.send_chat(f"Haetaan verkosta: <i>{arg}</i>...")
                results = self.bot.brain.searcher.search(arg)
                search_ctx = self.bot.brain.searcher.format_search_context(arg, results)
                if results:
                    summary_prompt = f"Tiivistä seuraavat hakutulokset hakusanalle '{arg}' suomeksi:\n\n{search_ctx}"
                    self.bot.say_stream(summary_prompt, user=sender['name'])
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
            if not arg:
                self.bot.send_chat("<b>Usage:</b> ?play &lt;query&gt; — or try ?recommend, ?surprise")
            elif self._is_vague_or_generic(arg):
                tracks, vibe = self._recommend_tracks(arg, 1)
                if tracks:
                    self._announce_tracks(tracks, vibe, arg)
                    for track in tracks:
                        self.bot.play(track)
            else:
                canonical = self._resolve_canonical(arg)
                try:
                    self._remember(canonical or arg)
                except Exception:
                    pass
                display = canonical or arg
                self.bot.send_chat(f"🎵 <b>Queued:</b> {display}")
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
        elif cmd == "?radio":
            if arg:
                self.bot.radio(arg)
            else:
                self.bot.send_chat("<b>Usage:</b> ?radio &lt;station name&gt;")

    # --- Music helpers ---------------------------------------------------

    def _recommender(self):
        try:
            return getattr(getattr(self.bot, "brain", None), "recommender", None)
        except Exception:
            return None

    def _chat_context(self):
        try:
            return getattr(self.bot, "recent_transcripts", None)
        except Exception:
            return None

    def _is_vague_or_generic(self, query):
        if not query or not query.strip():
            return True
        ql = query.strip().lower()
        if ql in GENERIC_MUSIC_QUERIES:
            return True
        recommender = self._recommender()
        try:
            result = recommender.is_generic_query(query) if recommender is not None else None
            if isinstance(result, bool) and result:
                return True
        except Exception:
            pass
        words = set(re.findall(r"\w+", ql))
        if words & set(VAGUE_MUSIC_WORDS):
            return True
        if " - " in ql:
            return False
        if re.search(r"\bby\b", ql) and len(ql.split()) <= 8:
            return False
        if ql in GENRE_WORDS:
            return True
        return False

    def _parse_recommend_args(self, arg):
        """Split '?recommend <vibe> [count]' into (description, count)."""
        text = (arg or "").strip()
        m = re.match(r"^(.*?)(?:\s+([2-5]))?\s*$", text)
        if not m:
            return text, 1
        desc = (m.group(1) or "").strip()
        count = int(m.group(2)) if m.group(2) else 1
        return desc, max(1, min(5, count))

    def _recommend_tracks(self, desc, count):
        """Return (tracks, vibe), tolerating older Brain APIs and mocks."""
        count = max(1, min(5, int(count or 1)))
        brain = getattr(self.bot, "brain", None)
        multi = getattr(brain, "recommend_songs", None)
        if callable(multi):
            try:
                result = multi(desc, chat_context=self._chat_context(), count=count)
                if isinstance(result, tuple) and len(result) == 2:
                    tracks, vibe = result
                    tracks = [t for t in (tracks or []) if isinstance(t, str) and t.strip()]
                    if tracks:
                        return tracks, vibe
            except Exception:
                pass
        # Fallback: single-track API, called repeatedly for variety.
        tracks, vibe = [], ""
        single = getattr(brain, "recommend_song", None)
        if not callable(single):
            return [], ""
        for _ in range(count):
            try:
                res = single(desc, chat_context=self._chat_context(), return_meta=True)
            except Exception:
                break
            song, v = (res if isinstance(res, tuple) else (res, ""))
            if isinstance(song, (list, tuple)):
                song = song[0] if song else None
            if not isinstance(song, str) or not song.strip():
                break
            if song not in tracks:
                tracks.append(song)
            vibe = vibe or v
            if len(tracks) >= 1 and count == 1:
                break
        return tracks, vibe

    def _announce_tracks(self, tracks, vibe, desc=None):
        if not tracks:
            return
        if len(tracks) == 1:
            msg = f"🎵 <b>Queued:</b> {tracks[0]}"
        else:
            lines = "<br/>".join(f"{i + 1}. {t}" for i, t in enumerate(tracks))
            msg = f"🎵 <b>Queued {len(tracks)} tracks:</b><br/>{lines}"
        if vibe:
            msg += f"<br/><i>Vibe: {vibe}</i>"
        try:
            self.bot.send_chat(msg)
        except Exception:
            pass

    def _resolve_canonical(self, query):
        try:
            recommender = self._recommender()
            if recommender is not None:
                resolved = recommender.resolve_track(query)
                if isinstance(resolved, str) and resolved.strip():
                    return resolved.strip()
        except Exception:
            pass
        return None

    def _remember(self, track):
        recommender = self._recommender()
        if recommender is not None:
            add = getattr(recommender, "add_to_history", None)
            if callable(add):
                result = add(track)
                # Guard against MagicMock returns — real impl returns None.
                return result

    def _get_history(self, count=10):
        try:
            recommender = self._recommender()
            if recommender is not None:
                hist = recommender.get_history(count)
                if isinstance(hist, list):
                    return [t for t in hist if isinstance(t, str)]
        except Exception:
            pass
        return []

    def _dislike_last(self):
        """Remove the last played track from rotation. Returns True if one was."""
        try:
            recommender = self._recommender()
            if recommender is None:
                return False
            last = getattr(recommender, "last_played", None)
            if not isinstance(last, str) or not last.strip():
                return False
            remove = getattr(recommender, "remove_from_history", None)
            if callable(remove):
                remove(last)
            return True
        except Exception:
            return False
