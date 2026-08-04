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



    def _strip_thinking(self, text: str) -> str:
        """Remove <think>...</think> blocks from LLM output."""
        if getattr(config, 'LLM_DISABLE_THINKING', False):
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()

    def _format_user_prompt(self, user_prompt: str) -> str:
        """Append /no_think suffix when thinking is disabled and using a Gemma 3 model."""
        model_setting = getattr(config, 'OLLAMA_MODEL', '').lower()
        if getattr(config, 'LLM_DISABLE_THINKING', False) and 'gemma-3' in model_setting:
            return f"{user_prompt} /no_think"
        return user_prompt

    def _chat_completion(self, messages, max_tokens=None, temperature=None, stop=None):
        """Send chat completion request to Ollama API or handle test mocks."""
        if max_tokens is None:
            max_tokens = getattr(config, 'LLM_MAX_TOKENS', 512)

        if hasattr(self.llm, 'create_chat_completion'):
            kwargs = {
                'messages': messages,
                'max_tokens': max_tokens
            }
            if stop is not None:
                kwargs['stop'] = stop
            if temperature is not None:
                kwargs['temperature'] = temperature
            return self.llm.create_chat_completion(**kwargs)

        if callable(self.llm):
            return self.llm(messages=messages, max_tokens=max_tokens)

        think_buffer = getattr(config, 'OLLAMA_THINK_BUFFER', 1024)
        num_predict = max_tokens + think_buffer if think_buffer else max_tokens

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
        no_think_instruction = " ÄLÄ tulosta ajattelulohkoja, <think>-tageja tai sisäistä päättelyä. Vastaa suoraan ilman niitä suomeksi." if getattr(config, 'LLM_DISABLE_THINKING', False) else ""

        web_context = self._build_search_context(user_prompt, search_context)
        if web_context:
            full_system = f"{base_system}{no_think_instruction}\nKonteksti: Kello on {now}.\n\n{web_context}"
        else:
            full_system = f"{base_system}{no_think_instruction}\nKonteksti: Kello on {now}."

        messages = [
            {"role": "system", "content": full_system}
        ]
        if self.memory_enabled:
            with self.lock:
                for msg in self.history:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        formatted_prompt = self._format_user_prompt(user_prompt)
        messages.append({"role": "user", "content": formatted_prompt})

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
            text = self._strip_thinking(text)
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
        no_think_instruction = " ÄLÄ tulosta ajattelulohkoja, <think>-tageja tai sisäistä päättelyä. Vastaa suoraan ilman niitä suomeksi." if getattr(config, 'LLM_DISABLE_THINKING', False) else ""

        web_context = self._build_search_context(user_prompt, search_context)
        if web_context:
            full_system = f"{base_system}{no_think_instruction}\nKonteksti: Kello on {now}.\n\n{web_context}"
        else:
            full_system = f"{base_system}{no_think_instruction}\nKonteksti: Kello on {now}."

        messages = [
            {"role": "system", "content": full_system}
        ]
        if self.memory_enabled:
            with self.lock:
                for msg in self.history:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        formatted_prompt = self._format_user_prompt(user_prompt)
        messages.append({"role": "user", "content": formatted_prompt})

        try:
            complete_response = ""
            in_think_block = False

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
                        if getattr(config, 'LLM_DISABLE_THINKING', False):
                            if '<think>' in complete_response and not in_think_block:
                                in_think_block = True
                            if in_think_block:
                                if '</think>' in complete_response:
                                    in_think_block = False
                                    after_think = complete_response.split('</think>', 1)[-1]
                                    if after_think:
                                        yield after_think
                                        complete_response = after_think
                                continue
                        yield token
            else:
                think_buffer = getattr(config, 'OLLAMA_THINK_BUFFER', 1024)
                num_predict = max_tokens + think_buffer if think_buffer else max_tokens

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

                yielded_any = False
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
                        if getattr(config, 'LLM_DISABLE_THINKING', False):
                            if '<think>' in complete_response and not in_think_block:
                                in_think_block = True
                            if in_think_block:
                                if '</think>' in complete_response:
                                    in_think_block = False
                                    after_think = complete_response.split('</think>', 1)[-1]
                                    if after_think:
                                        yielded_any = True
                                        yield after_think
                                        complete_response = after_think
                                continue
                        yielded_any = True
                        yield token

                # Fallback: If thinking ate all tokens or stream ended inside thinking block,
                # yield stripped content if nothing was yielded so the bot is never silent!
                if not yielded_any and complete_response:
                    fallback = self._strip_thinking(complete_response)
                    if fallback:
                        yield fallback

            final = self._strip_thinking(complete_response).strip().replace('"', '')
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
        lines = llm_output.strip().split('\n')
        intent = "OPEN"
        vibe = ""
        recommendations = []
        
        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line == "[INTENT]":
                current_section = "intent"
                continue
            elif line == "[VIBE]":
                current_section = "vibe"
                continue
            elif line == "[RECOMMENDATIONS]":
                current_section = "recommendations"
                continue
            
            if current_section == "intent":
                intent = line.upper()
            elif current_section == "vibe":
                vibe = line
            elif current_section == "recommendations":
                if " - " in line:
                    clean_line = re.sub(r'^\d+[\.\)\s-]*', '', line).strip()
                    clean_line = re.sub(r'^[\-\*•\s]*', '', clean_line).strip()
                    if clean_line:
                        recommendations.append(clean_line)
                        
        return intent, vibe, recommendations

    def recommend_song(self, description, chat_context=None, return_meta=False):
        """
        Fully LLM-driven music recommendation:
        1. Contextual vibe analysis using room chat history & user prompt.
        2. LLM DJ generation of candidate 'Artist - Track Title' songs and vibe summary.
        3. iTunes verification & standardization.
        4. History filtering.
        """
        system_content = (
            "Olet asiantunteva musiikki-DJ ja suosittelumoottori äänichat-hovimestarille.\n"
            "Analysoi viimeaikainen huoneen keskustelukonteksti ja käyttäjän pyyntö suositellaksesi kappaleita.\n"
            "Vastaa tiukasti seuraavassa muodossa:\n\n"
            "[INTENT]\n"
            "<SPECIFIC jos käyttäjä pyysi tiettyä kappaletta/artistia, GENRE_MOOD jos genrea/tunnelmaa pyydettiin, tai OPEN jos satunnainen/kontekstuaalinen>\n\n"
            "[VIBE]\n"
            "<Tiivis 1 lauseen tiivistelmä musiikin tunnelmasta suomeksi, esim. 'Energistä 80-luvun synthwavea myöhäisillan koodaukseen'>\n\n"
            "[RECOMMENDATIONS]\n"
            "1. Artistin Nimi - Kappaleen Nimi\n"
            "2. Artistin Nimi - Kappaleen Nimi\n"
            "3. Artistin Nimi - Kappaleen Nimi\n"
            "4. Artistin Nimi - Kappaleen Nimi\n"
        )

        fallback_tracks = [
            "Daft Punk - One More Time",
            "Queen - Bohemian Rhapsody",
            "The Midnight - Sunset",
            "Miles Davis - So What",
            "Kavinsky - Nightcall"
        ]

        if not self.llm:
            print("🧠 LLM is offline. Selecting from curated fallback catalog.")
            is_generic = not description or description.lower() in ("random music", "satunnainen musiikki", "musiikki")
            candidate_list = [description] if not is_generic and " - " in description else fallback_tracks
            song = self.recommender.get_recommendation(candidate_list)
            vibe_summary = f"Kuratoitu valikoima hakusanalle '{description}'" if not is_generic else "Kuratoitu klassinen tunnelma"
            return (song, vibe_summary) if return_meta else song

        context_str = ""
        if chat_context:
            recent = chat_context[-10:]
            context_str = " | ".join([f"{t['user']}: {t['text']}" for t in recent])
        else:
            context_str = "Ei viimeaikaisia viestejä."

        user_content = (
            f"Viimeaikainen keskustelukonteksti: {context_str}\n"
            f"Käyttäjän pyyntö: {description or 'Suosittele hyvää kappaletta huoneeseen'}\n"
            f"Luo tunnelmaan sopivia suosituksia."
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

        try:
            output = self._chat_completion(
                messages=messages,
                max_tokens=300,
                temperature=0.7
            )

            llm_text = self._strip_thinking(output['choices'][0]['message']['content'].strip())
            intent, vibe, recommendations = self.parse_recommendation_output(llm_text)
            
            print(f"🎵 Recommendation Intent: {intent}, Vibe: {vibe}")
            print(f"🎵 LLM Recommendations: {recommendations}")
            
            if not recommendations:
                print("⚠️ LLM didn't return formatted recommendations. Trying fallback track list.")
                candidate_list = [description] if description and " - " in description else fallback_tracks
                song = self.recommender.get_recommendation(candidate_list)
                vibe_summary = vibe or "Valittu tunnelman mukaan"
                return (song, vibe_summary) if return_meta else song

            is_specific = (intent == "SPECIFIC")
            selected_track = self.recommender.get_recommendation(
                recommendations,
                allow_history_override=is_specific
            )
            vibe_summary = vibe or "Valittu tunnelman mukaan"
            
            return (selected_track, vibe_summary) if return_meta else selected_track

        except Exception as e:
            print(f"⚠️ Recommendation error: {e}. Using fallback track selection.")
            song = self.recommender.get_recommendation(fallback_tracks)
            return (song, "Fallback-tunnelma") if return_meta else song


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
            return self._strip_thinking(output['choices'][0]['message']['content'].strip().replace('"', ''))
        except Exception as e:
            print(f"Report generation error: {e}")
            return f"Kello on {now}. Tilannetta ei voida arvioida käsittelyvirheen vuoksi."
