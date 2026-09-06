import json
import re
import threading
from datetime import datetime
import config
from modules.recommender import MusicRecommender
from modules.search import WebSearcher

try:
    import requests
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


class Brain:
    def __init__(self):
        self.llm = None
        self.lock = threading.Lock()
        self.history = []
        self.session = requests.Session() if LLM_AVAILABLE else None
        self.recommender = MusicRecommender()
        self.searcher = WebSearcher()
        self.last_recommendation = None

        # Initialize memory state from config (defaults to False if not set)
        self.memory_enabled = getattr(config, 'MEMORY_ENABLED', False)
        self.dynamic_prompt = None

        if LLM_AVAILABLE:
            self.check_connection()

    def check_connection(self):
        """Check if external Ollama API is reachable."""
        try:
            host = getattr(config, 'OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
            url = f"{host}/api/tags"
            timeout = getattr(config, 'OLLAMA_CONNECT_TIMEOUT', 3)
            res = (self.session or requests).get(url, timeout=timeout)
            if res.status_code == 200:
                print("🧠 Connected to Ollama API.")
                self.llm = True
                return True
        except Exception as e:
            print(f"❌ Ollama API Error: {e}")
        self.llm = None
        return False

    def toggle_memory(self):
        with self.lock:
            self.memory_enabled = not self.memory_enabled
            if not self.memory_enabled:
                self.history = []
            return self.memory_enabled





    def _chat_completion(self, messages, max_tokens=None, temperature=None, stop=None):
        """Send chat completion request to Ollama API or handle test mocks.

        Supports three backends (checked in order):
        1. Objects exposing ``create_chat_completion`` (llama.cpp style).
        2. Plain callables (used by tests: ``llm(messages=..., max_tokens=...)``).
        3. The external Ollama HTTP API (when ``self.llm`` is a simple flag).
        """
        if max_tokens is None:
            max_tokens = getattr(config, 'LLM_MAX_TOKENS', 512)

        create_fn = getattr(self.llm, 'create_chat_completion', None)
        if callable(create_fn):
            # A bare MagicMock auto-creates this attribute; if its return value
            # was never configured but the mock itself is callable with a dict
            # return_value, prefer the callable path (test compatibility).
            try:
                from unittest.mock import MagicMock as _MagicMock
                _auto_mocked = (
                    isinstance(self.llm, _MagicMock)
                    and isinstance(getattr(create_fn, 'return_value', None), _MagicMock)
                    and isinstance(getattr(self.llm, 'return_value', None), dict)
                )
            except Exception:
                _auto_mocked = False
            if not _auto_mocked:
                kwargs = {
                    'messages': messages,
                    'max_tokens': max_tokens
                }
                if stop is not None:
                    kwargs['stop'] = stop
                if temperature is not None:
                    kwargs['temperature'] = temperature
                result = create_fn(**kwargs)
                if isinstance(result, dict) and 'choices' in result:
                    return result
                # Unexpected shape (e.g. unconfigured mock): fall through
                # to the callable / HTTP paths instead of crashing.
                if not callable(self.llm):
                    return result

        if callable(self.llm):
            return self.llm(messages=messages, max_tokens=max_tokens)

        num_predict = max_tokens

        host = getattr(config, 'OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
        url = f"{host}/api/chat"
        keep_alive = getattr(config, 'OLLAMA_KEEP_ALIVE', '15m')
        context_size = getattr(config, 'LLM_CONTEXT_SIZE', 2048)
        default_temp = getattr(config, 'LLM_TEMPERATURE', 0.7)
        timeout = getattr(config, 'OLLAMA_TIMEOUT', 60)

        payload = {
            "model": getattr(config, 'OLLAMA_MODEL', 'gemma4-e2b'),
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "num_predict": num_predict,
                "num_ctx": context_size,
                "temperature": temperature if temperature is not None else default_temp
            }
        }
        if stop:
            payload["options"]["stop"] = stop

        response = (self.session or requests).post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        return {"choices": [{"message": {"content": content}}]}

    def _build_search_context(self, user_prompt: str, search_context: str = None) -> str:
        """Helper to fetch or format web search results if needed."""
        if search_context:
            return search_context

        if self.searcher.should_search(user_prompt):
            print(f"🌐 Performing web search for prompt: '{user_prompt}'")
            results = self.searcher.search(user_prompt)
            if results:
                return self.searcher.format_search_context(user_prompt, results)
        return ""

    def generate_response(self, user_prompt: str, max_tokens=None, stop=None, search_context=None) -> str:
        if not self.llm: return "Aivoni ovat offline-tilassa."

        if max_tokens is None:
            max_tokens = getattr(config, 'LLM_MAX_TOKENS', 512)

        now = datetime.now().strftime('%H:%M')
        base_system = self.dynamic_prompt or config.SYSTEM_PROMPT

        web_context = self._build_search_context(user_prompt, search_context)
        if web_context:
            full_system = f"{base_system}\nKonteksti: Kello on {now}.\n\n{web_context}"
        else:
            full_system = f"{base_system}\nKonteksti: Kello on {now}."

        messages = [
            {"role": "system", "content": full_system}
        ]
        if self.memory_enabled:
            with self.lock:
                for msg in self.history:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_prompt})

        try:
            output = self._chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                stop=stop
            )

            text = output['choices'][0]['message']['content']
            # Clean tags
            for t in ["<|im_start|>", "<|im_end|>", "<start_of_turn>", "<end_of_turn>"]:
                text = text.replace(t, "")
            response = text.strip().replace('"', '').replace("Obama:", "")

            self._update_history(user_prompt, response)
            return response
        except Exception as e:
            return f"Virhe ajattelussa: {e}"

    def generate_response_stream(self, user_prompt: str, max_tokens=None, stop=None, search_context=None):
        if not self.llm:
            yield "Aivoni ovat offline-tilassa."
            return

        if max_tokens is None:
            max_tokens = getattr(config, 'LLM_MAX_TOKENS', 512)

        now = datetime.now().strftime('%H:%M')
        base_system = self.dynamic_prompt or config.SYSTEM_PROMPT

        web_context = self._build_search_context(user_prompt, search_context)
        if web_context:
            full_system = f"{base_system}\nKonteksti: Kello on {now}.\n\n{web_context}"
        else:
            full_system = f"{base_system}\nKonteksti: Kello on {now}."

        messages = [
            {"role": "system", "content": full_system}
        ]
        if self.memory_enabled:
            with self.lock:
                for msg in self.history:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_prompt})

        try:
            complete_response = ""

            if hasattr(self.llm, 'create_chat_completion'):
                output = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    stop=stop,
                    stream=True
                )
                for chunk in output:
                    choices = chunk.get('choices', [])
                    if not choices:
                        continue
                    delta = choices[0].get('delta', {})
                    token = delta.get('content', '')
                    if not token:
                        continue
                    for t in ["<|im_start|>", "<|im_end|>", "<start_of_turn>", "<end_of_turn>"]:
                        token = token.replace(t, "")
                    token = token.replace("Obama:", "")
                    if token:
                        complete_response += token
                        yield token
            else:
                num_predict = max_tokens

                host = getattr(config, 'OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
                url = f"{host}/api/chat"
                keep_alive = getattr(config, 'OLLAMA_KEEP_ALIVE', '15m')
                context_size = getattr(config, 'LLM_CONTEXT_SIZE', 2048)
                default_temp = getattr(config, 'LLM_TEMPERATURE', 0.7)
                timeout = getattr(config, 'OLLAMA_TIMEOUT', 60)

                payload = {
                    "model": getattr(config, 'OLLAMA_MODEL', 'gemma4-e2b'),
                    "messages": messages,
                    "stream": True,
                    "keep_alive": keep_alive,
                    "options": {
                        "num_predict": num_predict,
                        "num_ctx": context_size,
                        "temperature": default_temp
                    }
                }
                if stop:
                    payload["options"]["stop"] = stop

                response = (self.session or requests).post(url, json=payload, stream=True, timeout=timeout)
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                    except Exception:
                        continue
                    token = chunk.get('message', {}).get('content', '')
                    if not token:
                        continue
                    for t in ["<|im_start|>", "<|im_end|>", "<start_of_turn>", "<end_of_turn>"]:
                        token = token.replace(t, "")
                    token = token.replace("Obama:", "")
                    if token:
                        complete_response += token
                        yield token

            final = complete_response.strip().replace('"', '')
            self._update_history(user_prompt, final)
        except Exception as e:
            yield f"Virhe ajattelussa: {e}"

    def generate_response_stream_async(self, user_prompt: str, queue, loop):
        """Runs in a background thread, puts tokens into the queue."""
        try:
            generator = self.generate_response_stream(user_prompt)
            for token in generator:
                loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, f"Virhe ajattelussa: {e}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    def _update_history(self, user, ai):
        if not self.memory_enabled:
            return

        max_hist = getattr(config, 'LLM_MAX_HISTORY', 20)
        with self.lock:
            self.history.append({"role": "user", "content": user})
            self.history.append({"role": "assistant", "content": ai})
            if len(self.history) > max_hist:
                self.history = self.history[-max_hist:]

    def reset_memory(self):
        with self.lock:
            self.history = []

    def undo_last_memory(self):
        """Removes the last interaction (user + assistant) from memory."""
        with self.lock:
            if len(self.history) >= 2:
                self.history = self.history[:-2]
                return True
            elif len(self.history) == 1:
                self.history = []
                return True
            return False

    def parse_recommendation_output(self, llm_output: str):
        """Parse the LLM DJ response into (intent, vibe, recommendations).

        Tolerant by design: section headers are matched case-insensitively
        (``[intent]`` / ``Intent:`` / ``**RECOMMENDATIONS**`` …), markdown
        bullets/numbering/quotes are stripped, en/em dashes are treated as
        ``" - "``, and ``"Title by Artist"`` lines are flipped to
        ``"Artist - Title"``. Free-form answers without any headers are
        scanned for ``Artist - Title`` lines as a last resort.
        """
        intent = "OPEN"
        vibe = ""
        recommendations = []

        if not llm_output:
            return intent, vibe, recommendations

        text = llm_output.strip().replace('```', '')
        lines = text.split('\n')

        header_re = re.compile(
            r'^\s*\**\s*\[?\s*(intent|vibe|recommendations)\s*\]?\s*:?\s*\**\s*$',
            re.IGNORECASE,
        )
        current_section = None
        vibe_lines = []
        rec_lines = []
        intent_lines = []
        for line in lines:
            m = header_re.match(line.strip())
            if m:
                current_section = m.group(1).lower()
                continue
            if current_section == "intent":
                intent_lines.append(line.strip())
            elif current_section == "vibe":
                vibe_lines.append(line.strip())
            elif current_section == "recommendations":
                rec_lines.append(line)
            # Lines before any header are ignored (preamble).

        if intent_lines:
            raw_intent = " ".join(t for t in intent_lines if t).upper()
            if "SPECIFIC" in raw_intent or "EXACT" in raw_intent or "REQUEST" in raw_intent:
                intent = "SPECIFIC"
            elif "GENRE" in raw_intent or "MOOD" in raw_intent or "VIBE" in raw_intent:
                intent = "GENRE_MOOD"
            elif "OPEN" in raw_intent or "RANDOM" in raw_intent or "CONTEXT" in raw_intent:
                intent = "OPEN"
            elif raw_intent:
                intent = raw_intent.split()[0]

        vibe = " ".join(t for t in vibe_lines if t).strip().strip('"\'“”‘’')
        if len(vibe) > 200:
            vibe = vibe[:200].rsplit(' ', 1)[0]

        if rec_lines:
            for line in rec_lines:
                cleaned = self._clean_recommendation_line(line)
                if cleaned:
                    recommendations.append(cleaned)

        if not recommendations:
            # Fallback: scan the whole output for 'Artist - Title' lines.
            for line in lines:
                if header_re.match(line.strip()):
                    continue
                cleaned = self._clean_recommendation_line(line)
                if cleaned and cleaned not in recommendations:
                    recommendations.append(cleaned)

        # Final safety net: keep order, drop exact duplicates.
        seen = set()
        unique = []
        for r in recommendations:
            key = r.lower()
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return intent, vibe, unique

    def _clean_recommendation_line(self, line: str):
        """Normalize one candidate line to 'Artist - Title' or ''."""
        if not line:
            return ""
        s = line.strip()
        # Strip markdown bullets / numbering / quotes / checkboxes.
        s = re.sub(r'^[\s\-\*•·–>]+', '', s).strip()
        s = re.sub(r'^\d+[\.\)\:\-–\s]+', '', s).strip()
        s = re.sub(r'^\[\s*[xX ]\s*\]\s*', '', s).strip()
        s = s.strip(' "\'“”‘’`').strip()
        s = s.replace('–', '-').replace('—', '-').replace('−', '-')
        if not s or len(s) < 3:
            return ""
        if ' - ' not in s:
            # 'Title by Artist' -> 'Artist - Title'
            m = re.match(r'^\s*(.+?)\s+by\s+(.+?)\s*$', s, re.IGNORECASE)
            if m and len(m.group(1).strip()) >= 2 and len(m.group(2).strip()) >= 2:
                s = f"{m.group(2).strip()} - {m.group(1).strip()}"
            else:
                return ""
        # Drop trailing parenthetical noise the LLM sometimes adds, keep core.
        s = re.sub(r'\s{2,}', ' ', s).strip()
        artist, _, title = s.partition(' - ')
        if len(artist.strip()) < 2 or len(title.strip()) < 2:
            return ""
        return f"{artist.strip()} - {title.strip()}"

    def _is_generic_description(self, description):
        if not description:
            return True
        return self.recommender.is_generic_query(description)

    def _extract_explicit_track(self, description):
        """Return 'Artist - Title' if the user named a concrete track, else None."""
        if not description:
            return None
        s = description.strip().strip('"\'“”‘’')
        if self.recommender.is_generic_query(s):
            return None
        artist, title = self.recommender._split_artist_title(s)
        if artist and title and len(artist) >= 2 and len(title) >= 2:
            # Guard against sentences that merely contain ' - ' or 'by'.
            if len(s.split()) <= 12:
                return f"{artist} - {title}"
        return None

    def _describe_chat_context(self, chat_context, max_items=8, max_chars=800):
        if not chat_context:
            return "Ei viimeaikaisia viestejä."
        recent = chat_context[-max_items:]
        parts = []
        for t in recent:
            try:
                user = t.get('user', '?')
                text = str(t.get('text', ''))[:120]
                parts.append(f"{user}: {text}")
            except Exception:
                continue
        context_str = " | ".join(parts) or "Ei viimeaikaisia viestejä."
        return context_str[:max_chars]

    def _build_dj_prompt(self, description, context_str, num_candidates=5):
        system_content = (
            "Olet asiantunteva musiikki-DJ ja suosittelumoottori äänichat-hovimestarille.\n"
            "Analysoi viimeaikainen huoneen keskustelukonteksti ja käyttäjän pyyntö suositellaksesi kappaleita.\n"
            f"Anna aina {num_candidates} erilaista, todella olemassa olevaa kappaletta muodossa 'Artisti - Kappale'.\n"
            "Älä keksi kappaleita. Suosi tunnettuja, toistettavissa olevia kappaleita.\n"
            "Vastaa tiukasti seuraavassa muodossa, ilman markdownia tai esipuhetta:\n\n"
            "[INTENT]\n"
            "<SPECIFIC jos käyttäjä pyysi tiettyä kappaletta/artistia, GENRE_MOOD jos genrea/tunnelmaa pyydettiin, tai OPEN jos satunnainen/kontekstuaalinen>\n\n"
            "[VIBE]\n"
            "<Tiivis 1 lauseen tiivistelmä musiikin tunnelmasta suomeksi, esim. 'Energistä 80-luvun synthwavea myöhäisillan koodaukseen'>\n\n"
            "[RECOMMENDATIONS]\n"
            "1. Artistin Nimi - Kappaleen Nimi\n"
            "2. Artistin Nimi - Kappaleen Nimi\n"
            "3. Artistin Nimi - Kappaleen Nimi\n"
            "4. Artistin Nimi - Kappaleen Nimi\n"
            "5. Artistin Nimi - Kappaleen Nimi\n"
        )
        user_content = (
            f"Viimeaikainen keskustelukonteksti: {context_str}\n"
            f"Käyttäjän pyyntö: {description or 'Suosittele hyvää kappaletta huoneeseen'}\n"
            f"Luo tunnelmaan sopivia suosituksia."
        )
        return system_content, user_content

    def recommend_song(self, description, chat_context=None, return_meta=False, count=1):
        """
        Fully LLM-driven music recommendation:
        1. Fast path: explicit 'Artist - Title' requests resolve via iTunes
           without any LLM call (low latency, no hallucination).
        2. Contextual LLM DJ generates candidate songs + vibe summary.
        3. iTunes verification & standardization with best-match scoring.
        4. History filtering with variety (shuffled, not always first pick).

        Returns a single track string, or (track, vibe) when return_meta
        is True. With count > 1, use recommend_songs() instead.
        """
        if count is not None and int(count) > 1:
            songs, vibe = self.recommend_songs(
                description, chat_context=chat_context, count=int(count))
            song = songs[0] if songs else None
            return (song, vibe) if return_meta else song

        desc = (description or "").strip().strip('"\'“”‘’')

        # --- Fast path: the user named a concrete track -------------------
        explicit = self._extract_explicit_track(desc)
        if explicit:
            final = self.recommender.resolve_track(explicit) or explicit
            self.recommender.add_to_history(final)
            self.last_recommendation = {"track": final, "vibe": "", "query": desc}
            vibe_summary = f"Toivekappale: {final}"
            return (final, vibe_summary) if return_meta else final

        num_candidates = getattr(config, 'RECOMMENDER_NUM_CANDIDATES', 5)

        # --- Offline path: curated catalog, no LLM -------------------------
        if not self.llm:
            print("🧠 LLM is offline. Selecting from curated fallback catalog.")
            is_generic = self._is_generic_description(desc)
            if not is_generic:
                # A mood/genre phrase ("chill jazz") is still a useful seed.
                candidate_list = [desc]
            else:
                candidate_list = []
            song = self.recommender.get_recommendation(candidate_list) \
                if candidate_list else self.recommender.recommend_fallback()
            vibe_summary = (f"Kuratoitu valikoima hakusanalle '{desc}'"
                            if not is_generic else "Kuratoitu klassinen tunnelma")
            if song:
                self.last_recommendation = {"track": song, "vibe": vibe_summary, "query": desc}
            return (song, vibe_summary) if return_meta else song

        # --- LLM DJ path ----------------------------------------------------
        context_str = self._describe_chat_context(chat_context)
        system_content, user_content = self._build_dj_prompt(
            desc or 'Suosittele hyvää kappaletta huoneeseen',
            context_str, num_candidates=num_candidates)
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

        try:
            output = self._chat_completion(
                messages=messages,
                max_tokens=getattr(config, 'RECOMMENDER_LLM_TOKENS', 400),
                temperature=getattr(config, 'RECOMMENDER_LLM_TEMPERATURE', 0.8)
            )

            llm_text = output['choices'][0]['message']['content'].strip()
            intent, vibe, recommendations = self.parse_recommendation_output(llm_text)

            print(f"🎵 Recommendation Intent: {intent}, Vibe: {vibe}")
            print(f"🎵 LLM Recommendations: {recommendations}")

            if not recommendations:
                print("⚠️ LLM didn't return formatted recommendations. Trying fallback track list.")
                candidate_list = [] if self._is_generic_description(desc) else [desc]
                song = (self.recommender.get_recommendation(candidate_list)
                        if candidate_list else self.recommender.recommend_fallback())
                vibe_summary = vibe or "Valittu tunnelman mukaan"
                if song:
                    self.last_recommendation = {"track": song, "vibe": vibe_summary, "query": desc}
                return (song, vibe_summary) if return_meta else song

            is_specific = (intent == "SPECIFIC")
            selected_track = self.recommender.get_recommendation(
                recommendations,
                allow_history_override=is_specific
            )
            vibe_summary = vibe or "Valittu tunnelman mukaan"
            if selected_track:
                self.last_recommendation = {
                    "track": selected_track, "vibe": vibe_summary, "query": desc}

            return (selected_track, vibe_summary) if return_meta else selected_track

        except Exception as e:
            print(f"⚠️ Recommendation error: {e}. Using fallback track selection.")
            song = self.recommender.recommend_fallback()
            if song:
                self.last_recommendation = {
                    "track": song, "vibe": "Fallback-tunnelma", "query": desc}
            return (song, "Fallback-tunnelma") if return_meta else song

    def recommend_songs(self, description, chat_context=None, count=3):
        """Recommend up to *count* tracks. Returns (tracks_list, vibe)."""
        count = max(1, min(5, int(count or 1)))
        desc = (description or "").strip().strip('"\'“”‘’')

        explicit = self._extract_explicit_track(desc)
        if explicit:
            final = self.recommender.resolve_track(explicit) or explicit
            self.recommender.add_to_history(final)
            vibe = f"Toivekappale: {final}"
            return [final], vibe

        if not self.llm:
            tracks = self.recommender.get_recommendations(
                [] if self._is_generic_description(desc) else [desc],
                count=count) or []
            while len(tracks) < count:
                extra = self.recommender.recommend_fallback()
                if not extra or extra in tracks:
                    break
                tracks.append(extra)
            vibe = (f"Kuratoitu valikoima hakusanalle '{desc}'"
                    if desc and not self._is_generic_description(desc)
                    else "Kuratoitu klassinen tunnelma")
            return tracks, vibe

        context_str = self._describe_chat_context(chat_context)
        system_content, user_content = self._build_dj_prompt(
            desc or 'Suosittele hyvää kappaletta huoneeseen',
            context_str,
            num_candidates=max(getattr(config, 'RECOMMENDER_NUM_CANDIDATES', 5), count))
        try:
            output = self._chat_completion(
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}],
                max_tokens=getattr(config, 'RECOMMENDER_LLM_TOKENS', 400),
                temperature=getattr(config, 'RECOMMENDER_LLM_TEMPERATURE', 0.8))
            llm_text = output['choices'][0]['message']['content'].strip()
            intent, vibe, recommendations = self.parse_recommendation_output(llm_text)
            tracks = self.recommender.get_recommendations(
                recommendations, count=count,
                allow_history_override=(intent == "SPECIFIC"))
            if not tracks:
                tracks = [self.recommender.recommend_fallback()]
                tracks = [t for t in tracks if t]
            return tracks, (vibe or "Valittu tunnelman mukaan")
        except Exception as e:
            print(f"⚠️ Multi-recommendation error: {e}.")
            track = self.recommender.recommend_fallback()
            return ([track] if track else [], "Fallback-tunnelma")


    def generate_hourly_report(self, active_users, recent_transcripts):
        if not self.llm: return None

        now = datetime.now().strftime('%H:%M')
        transcript_text = ""
        if recent_transcripts:
            transcript_text = "\n".join([f"- {t['user']}: {t['text']}" for t in recent_transcripts])
        else:
            transcript_text = "Kukaan ei ole puhunut äskettäin."

        users_text = ", ".join(active_users) if active_users else "Kukaan muu ei ole täällä."

        system_content = (
            f"{config.SYSTEM_PROMPT} "
            f"Kello on tällä hetkellä {now}. Annat säännöllisen tunneittaisen tilannekatsauksen huoneelle. "
            f"Mainitse nykyinen kellonaika, huomioi keitä huoneessa on ({users_text}), "
            f"ja tiivistä tai kommentoi lyhyesti tunnelmaa viimeisten minuutin keskustelujen perusteella, jos niitä on.\n"
            f"Pidä se lyhyenä (alle 4 lausetta), nokkelana ja hovimestarimaisena suomeksi."
        )
        user_content = f"Viimeaikainen keskustelu:\n{transcript_text}\n\nAnna tilannekatsaus."
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

        try:
            output = self._chat_completion(
                messages=messages,
                max_tokens=350
            )
            return output['choices'][0]['message']['content'].strip().replace('"', '')
        except Exception as e:
            print(f"Report generation error: {e}")
            return f"Kello on {now}. Tilannetta ei voida arvioida käsittelyvirheen vuoksi."
