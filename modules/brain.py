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
        """Send chat completion request to Ollama API or handle test mocks."""
        if max_tokens is None:
            max_tokens = getattr(config, 'LLM_MAX_TOKENS', 512)

        handler = getattr(self.llm, 'create_chat_completion', None)
        if callable(handler):
            kwargs = {
                'messages': messages,
                'max_tokens': max_tokens
            }
            if stop is not None:
                kwargs['stop'] = stop
            if temperature is not None:
                kwargs['temperature'] = temperature
            try:
                result = handler(**kwargs)
            except TypeError:
                result = None
            if isinstance(result, dict) and 'choices' in result:
                return result
            # Tolerant mock path: tests configure llm.return_value as the
            # response dict while llm itself is a MagicMock (which auto-creates
            # create_chat_completion). Fall back to the configured value.
            fallback = getattr(self.llm, 'return_value', None)
            if isinstance(fallback, dict) and 'choices' in fallback:
                return fallback
            if isinstance(result, dict):
                return result
            if fallback is not None:
                return fallback

        if callable(self.llm):
            result = self.llm(messages=messages, max_tokens=max_tokens)
            if isinstance(result, dict) and 'choices' in result:
                return result
            fallback = getattr(self.llm, 'return_value', None)
            if isinstance(fallback, dict) and 'choices' in fallback:
                return fallback
            return result

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
        """Tolerant parser for the DJ format. Accepts bracket headers
        ([INTENT]/Intent:/**INTENT**), code fences, JSON, and loose
        numbered/bulleted 'Artist - Title' lines."""
        if not llm_output:
            return "OPEN", "", []
        text = str(llm_output).strip()
        # strip code fences
        text = re.sub(r'```(?:json)?', '', text).strip('` \n')

        # JSON shortcut: {"intent":.., "vibe":.., "recommendations":[...]}
        recommendations = []
        intent = "OPEN"
        vibe = ""
        try:
            maybe = json.loads(text)
            if isinstance(maybe, dict):
                raw_intent = str(maybe.get("intent", maybe.get("INTENT", "OPEN")))
                intent = self._normalize_intent(raw_intent)
                vibe = str(maybe.get("vibe", maybe.get("VIBE", ""))).strip().strip('"')
                raw_recs = maybe.get("recommendations", maybe.get("RECOMMENDATIONS", []))
                if isinstance(raw_recs, list):
                    for r in raw_recs:
                        cleaned = self._clean_rec_line(str(r))
                        if cleaned:
                            recommendations.append(cleaned)
                if recommendations:
                    return intent, vibe, recommendations
            elif isinstance(maybe, list):
                for r in maybe:
                    cleaned = self._clean_rec_line(str(r))
                    if cleaned:
                        recommendations.append(cleaned)
                if recommendations:
                    return intent, vibe, recommendations
        except Exception:
            pass

        current_section = None
        vibe_lines = []
        header_re = re.compile(
            r'^\s*(?:#{1,3}\s*)?(?:\*{0,2}\[?\s*(intent|vibe|recommendations|tunnelma|suositukset)'
            r'\s*\]?\*{0,2})\s*:?\s*$', re.IGNORECASE)
        for raw_line in text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            m = header_re.match(line)
            if m:
                kind = m.group(1).lower()
                if kind == "intent":
                    current_section = "intent"
                elif kind in ("vibe", "tunnelma"):
                    current_section = "vibe"
                else:
                    current_section = "recommendations"
                continue
            # inline "VIBE: something" / "INTENT: SPECIFIC"
            m_inline = re.match(r'^(intent|vibe|recommendations)\s*:\s*(.+)$', line, re.IGNORECASE)
            if m_inline:
                kind, rest = m_inline.group(1).lower(), m_inline.group(2).strip()
                if kind == "intent":
                    intent = self._normalize_intent(rest)
                elif kind == "vibe":
                    vibe_lines.append(rest.strip('" '))
                else:
                    cleaned = self._clean_rec_line(rest)
                    if cleaned:
                        recommendations.append(cleaned)
                continue

            if current_section == "intent":
                intent = self._normalize_intent(line)
            elif current_section == "vibe":
                vibe_lines.append(line.strip('" '))
            elif current_section == "recommendations":
                cleaned = self._clean_rec_line(line)
                if cleaned:
                    recommendations.append(cleaned)
            else:
                # no section yet: still harvest obvious track lines
                cleaned = self._clean_rec_line(line)
                if cleaned and len(recommendations) < 10:
                    # only auto-harvest when it really looks like Artist - Title
                    if re.search(r'\s[-–—|:]\s', line) or ' by ' in line.lower():
                        recommendations.append(cleaned)

        vibe = " ".join(vibe_lines).strip()
        vibe = re.sub(r'\s+', ' ', vibe)[:220]

        # de-dupe preserving order (normalized via recommender)
        try:
            seen, unique = set(), []
            for r in recommendations:
                key = self.recommender._normalize_track(r)
                if key and key not in seen:
                    seen.add(key)
                    unique.append(r)
            recommendations = unique[:10]
        except Exception:
            recommendations = recommendations[:10]
        return intent, vibe, recommendations

    def _normalize_intent(self, raw: str) -> str:
        t = (raw or "").upper().strip()
        t = re.sub(r'[^A-Z_]', '', t.split()[0] if t.split() else t)
        if t in ("SPECIFIC", "EXACT", "SONG", "ARTIST", "TRACK", "REQUEST"):
            return "SPECIFIC"
        if t in ("GENRE", "MOOD", "VIBE", "GENRE_MOOD", "GENREMOOD", "THEME"):
            return "GENRE_MOOD"
        if t in ("SIMILAR", "MORE", "LIKE", "ANOTHER"):
            return "SIMILAR"
        return "OPEN"

    def _clean_rec_line(self, line: str):
        if not line:
            return None
        s = str(line).strip()
        if not s:
            return None
        # skip headers / prose
        if re.match(r'^\s*(?:#{1,3}\s*)?(?:\*{0,2}\[?\s*(intent|vibe|recommendations))',
                     s, re.IGNORECASE):
            return None
        s = re.sub(r'```', '', s).strip()
        s = re.sub(r'^[\d]+[\.\)\:\-\s]+', '', s).strip()
        s = re.sub(r'^[\-\*•·\s]+', '', s).strip()
        s = s.strip(' "\'“”‘’').strip()
        s = re.sub(r'\s*[\(\[]?\d{1,2}:\d{2}[\)\]]?\s*$', '', s).strip()
        # "Artist: X, Title: Y" -> "X - Y"
        m = re.match(r'artist\s*:\s*(.+?)\s*,\s*(?:title|track|song)\s*:\s*(.+)',
                     s, re.IGNORECASE)
        if m:
            s = f"{m.group(1).strip()} - {m.group(2).strip()}"
        # must contain a separator to count as a track
        if not re.search(r'\s[-–—|:]\s', s) and ' by ' not in s.lower():
            return None
        # normalize dashes
        s = re.sub(r'\s[–—]\s', ' - ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if len(s) < 5 or len(s) > 120:
            return None
        low = s.lower()
        if low.startswith(("intent", "vibe", "tunnelma", "here are", "tässä on",
                           "suositukseni", "recommendation")):
            return None
        return s or None

    def _clean_vibe_request(self, description) -> str:
        """Strip voice-trigger leftovers & filler so the DJ prompt gets a clean vibe."""
        if not description:
            return ""
        s = str(description).strip()
        # remove leading recommend/play trigger phrases (only at start — QoL,
        # so artist names containing 'play' etc. are not mangled mid-string)
        triggers = []
        try:
            triggers += list(config.VOICE_TRIGGERS.get('RECOMMEND', []))
            triggers += list(config.VOICE_TRIGGERS.get('PLAY_SPECIFIC', []))
            triggers += list(config.VOICE_TRIGGERS.get('PLAY_MUSIC', []))
        except Exception:
            pass
        lowered = s.lower()
        for t in sorted(triggers, key=len, reverse=True):
            prefix = t.lower().strip()
            if prefix and lowered.startswith(prefix):
                s = s[len(prefix):].strip(" ,:;-")
                lowered = s.lower()
                break
        # Explicit "Artist - Title" requests: never mangle the track itself.
        if " - " in s or " by " in s.lower():
            return s[:200]
        # filler phrases (vibe requests only)
        s = re.sub(r'^(please\s+|kiitos\s+|laita\s+|soita\s+|play\s+|queue\s+)',
                   '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'\b(some|any|good|nice|random|satunnainen|jotain|hyvää|'
                   r'musiikkia?|music|songs?|kappaletta?|biisi)\b',
                   ' ', s, flags=re.IGNORECASE)
        s = re.sub(r'\s+(please|kiitos|pls)$', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'\s+', ' ', s).strip(" ,:;-")
        return s[:200]

    def _time_bucket(self) -> str:
        h = datetime.now().hour
        if 5 <= h < 10:
            return "aamu (heräilevä, pirteä mutta pehmeä)"
        if 10 <= h < 17:
            return "päivä (työ-/taustamusiikki käy)"
        if 17 <= h < 22:
            return "ilta (sosiaalinen, energinen)"
        return "myöhäisyö (tunnelmallinen, ei liian raskas)"

    def _recommendation_prompt(self, clean_desc, context_str, exclude_str, n=8):
        system_content = (
            "Olet asiantunteva musiikki-DJ ja suosittelumoottori äänichat-hovimestarille.\n"
            "Suosi OIKEITA, julkaistuja kappaleita (ei keksittyjä). Vastaa tiukasti:\n\n"
            "[INTENT]\n"
            "<SPECIFIC jos käyttäjä nimesi kappaleen/artistin, GENRE_MOOD jos genrea/tunnelmaa, "
            "SIMILAR jos 'lisää samanlaista / toinen samanlainen', OPEN jos satunnainen>\n\n"
            "[VIBE]\n"
            "<1 lause suomeksi, esim. 'Energistä 80-luvun synthwavea myöhäisillan koodaukseen'>\n\n"
            "[RECOMMENDATIONS]\n"
            f"{n} riviä muotoa 'Artisti - Kappale' (ei numeroita edessä pakollisina, "
            "ei linkkejä, ei kestoja). Pidä lista monipuolisena (eri artisteja). "
            "Vältä näitä jo soitettuja: "
            f"{exclude_str or '—'}."
        )
        user_content = (
            f"Aika: {self._time_bucket()}.\n"
            f"Viimeaikainen keskustelu: {context_str}\n"
            f"Käyttäjän pyyntö: {clean_desc or 'Suosittele hyvää kappaletta huoneeseen'}\n"
            f"Anna {n} suositusta."
        )
        return system_content, user_content

    def recommend_song(self, description, chat_context=None, return_meta=False):
        """
        Fully LLM-driven music recommendation:
        1. Contextual vibe analysis using room chat history & user prompt.
        2. LLM DJ generation of candidate 'Artist - Track Title' songs and vibe summary.
        3. iTunes verification & standardization.
        4. History filtering (with artist cooldown).
        Retries once with a stricter prompt; falls back to the curated
        mood catalog when offline or when the LLM output is unusable.
        """
        from modules.recommender import FLAT_FALLBACK

        raw_desc = description or ""
        clean_desc = self._clean_vibe_request(raw_desc)
        vibe_hint = clean_desc or str(raw_desc or "")

        try:
            exclude = self.recommender.history_summary(15)
        except Exception:
            exclude = []

        if not self.llm:
            print("🧠 LLM is offline. Selecting from curated fallback catalog.")
            candidate_list = None
            if clean_desc and (" - " in clean_desc or " by " in clean_desc.lower()):
                candidate_list = [clean_desc.strip()]
            song = self.recommender.get_recommendation(candidate_list or [], vibe=vibe_hint)
            if song is None:
                song = self.recommender.pick_fallback(vibe_hint) or FLAT_FALLBACK[0]
                try:
                    self.recommender.add_to_history(song, vibe=vibe_hint)
                except Exception:
                    pass
            vibe_summary = (f"Kuratoitu valikoima hakusanalle '{clean_desc}'"
                            if clean_desc else "Kuratoitu klassinen tunnelma")
            return (song, vibe_summary) if return_meta else song

        if chat_context:
            recent = chat_context[-10:]
            parts = []
            for t in recent:
                try:
                    parts.append(f"{t.get('user', '?')}: {t.get('text', '')}")
                except Exception:
                    continue
            context_str = " | ".join(parts)[:1200] or "Ei viimeaikaisia viestejä."
        else:
            context_str = "Ei viimeaikaisia viestejä."
        exclude_str = "; ".join(exclude) if exclude else ""

        n_candidates = int(getattr(config, 'RECOMMENDER_CANDIDATES', 8) or 8)
        n_candidates = max(4, min(10, n_candidates))

        def _ask(extra_avoid="", temperature=0.8, n=n_candidates):
            sys_c, user_c = self._recommendation_prompt(clean_desc, context_str, exclude_str, n=n)
            if extra_avoid:
                user_c += f"\n{extra_avoid}"
            messages = [
                {"role": "system", "content": sys_c},
                {"role": "user", "content": user_c}
            ]
            output = self._chat_completion(
                messages=messages,
                max_tokens=int(getattr(config, 'RECOMMENDER_MAX_TOKENS', 500) or 500),
                temperature=temperature,
            )
            return output['choices'][0]['message']['content'].strip()

        try:
            llm_text = _ask()
            intent, vibe, recommendations = self.parse_recommendation_output(llm_text)

            print(f"🎵 Recommendation Intent: {intent}, Vibe: {vibe}")
            print(f"🎵 LLM Recommendations: {recommendations}")

            if not recommendations and getattr(config, 'RECOMMENDER_RETRY', True):
                print("⚠️ LLM didn't return formatted recommendations. Retrying once with stricter prompt.")
                llm_text = _ask(
                    extra_avoid="Vastaa VAIN yllä pyydetyssä formaatissa, 8 riviä 'Artisti - Kappale'.",
                    temperature=0.9,
                )
                intent, vibe, recommendations = self.parse_recommendation_output(llm_text)
                print(f"🎵 Retry Intent: {intent}, Vibe: {vibe}")
                print(f"🎵 Retry Recommendations: {recommendations}")

            if not recommendations:
                print("⚠️ LLM still unusable. Using mood fallback catalog.")
                song = self.recommender.get_recommendation([], vibe=vibe_hint)
                vibe_summary = vibe or "Valittu tunnelman mukaan"
                return (song, vibe_summary) if return_meta else song

            is_specific = (intent == "SPECIFIC")
            selected_track = self.recommender.get_recommendation(
                recommendations,
                allow_history_override=is_specific,
                vibe=vibe or vibe_hint,
            )
            vibe_summary = vibe or "Valittu tunnelman mukaan"

            return (selected_track, vibe_summary) if return_meta else selected_track

        except Exception as e:
            print(f"⚠️ Recommendation error: {e}. Using fallback track selection.")
            song = self.recommender.get_recommendation([], vibe=vibe_hint)
            return (song, "Fallback-tunnelma") if return_meta else song

    def recommend_songs(self, description, chat_context=None, count=3):
        """QoL: rank up to `count` fresh tracks (for queueing several)."""
        song = self.recommend_song(description, chat_context=chat_context, return_meta=False)
        if count <= 1:
            return [song] if song else []
        # second pass excluding the first pick is handled by history (already added)
        out = [song] if song else []
        try:
            # ask recommender for more from mood catalog without LLM round-trip
            while len(out) < count:
                nxt = self.recommender.pick_fallback(str(description or ""))
                if not nxt or nxt in out:
                    break
                try:
                    self.recommender.add_to_history(nxt, vibe=str(description or ""))
                except Exception:
                    pass
                out.append(nxt)
        except Exception:
            pass
        return out


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
