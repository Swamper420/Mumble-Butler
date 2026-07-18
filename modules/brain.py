import re
import threading
from datetime import datetime
import random
import config
from modules.recommender import MusicRecommender

try:
    from llama_cpp import Llama
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

class Brain:
    def __init__(self):
        self.llm = None
        self.lock = threading.Lock()
        self.history = []
        self.recommender = MusicRecommender()

        # Initialize memory state from config (defaults to False if not set)
        self.memory_enabled = getattr(config, 'MEMORY_ENABLED', False)
        self.dynamic_prompt = None

        if LLM_AVAILABLE:
            try:
                print("🧠 Loading LLM...")
                self.llm = Llama(
                    model_path=config.LLM_MODEL_PATH,
                    n_ctx=config.LLM_CONTEXT_SIZE,
                    n_gpu_layers=config.LLM_GPU_LAYERS,
                    verbose=False
                )
            except Exception as e:
                print(f"❌ LLM Error: {e}")

    def toggle_memory(self):
        with self.lock:
            self.memory_enabled = not self.memory_enabled
            if not self.memory_enabled:
                self.history = [] # Optional: clear history when disabling?
            return self.memory_enabled

    def _get_tags(self):
        fmt = getattr(config, 'LLM_PROMPT_FORMAT', 'chatml').lower()
        # Auto-detect ChatML format for Qwen models if default 'gemma' is selected
        if fmt == 'gemma' and 'qwen' in getattr(config, 'LLM_MODEL_PATH', '').lower():
            fmt = 'chatml'

        if fmt == 'gemma':
            return {
                'system_start': '<start_of_turn>system\n',
                'system_end': '<end_of_turn>\n',
                'user_start': '<start_of_turn>user\n',
                'user_end': '<end_of_turn>\n',
                'assistant_start': '<start_of_turn>model\n',
                'assistant_end': '<end_of_turn>\n',
                'stop': ['<end_of_turn>', '<start_of_turn>']
            }
        else: # default to chatml
            return {
                'system_start': '<|im_start|>system\n',
                'system_end': '<|im_end|>\n',
                'user_start': '<|im_start|>user\n',
                'user_end': '<|im_end|>\n',
                'assistant_start': '<|im_start|>assistant\n',
                'assistant_end': '<|im_end|>\n',
                'stop': ['<|im_end|>', '<|im_start|>']
            }


    def _strip_thinking(self, text: str) -> str:
        """Remove <think>...</think> blocks from LLM output."""
        if config.LLM_DISABLE_THINKING:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()

    def _format_user_prompt(self, user_prompt: str) -> str:
        """Append /no_think suffix when thinking is disabled and using a Gemma model."""
        if config.LLM_DISABLE_THINKING and 'gemma' in getattr(config, 'LLM_MODEL_PATH', '').lower():
            return f"{user_prompt} /no_think"
        return user_prompt

    def generate_response(self, user_prompt: str, max_tokens=120) -> str:
        if not self.llm: return "My brain is offline."

        tags = self._get_tags()
        now = datetime.now().strftime('%H:%M')
        base_system = self.dynamic_prompt or config.SYSTEM_PROMPT
        full_system = f"{base_system}\nContext: It is {now}."

        history_str = ""
        # Only include history if memory is enabled
        if self.memory_enabled:
            with self.lock:
                for msg in self.history:
                    role_start = tags['user_start'] if msg['role'] == 'user' else tags['assistant_start']
                    role_end = tags['user_end'] if msg['role'] == 'user' else tags['assistant_end']
                    history_str += f"{role_start}{msg['content']}{role_end}"

        formatted_prompt = self._format_user_prompt(user_prompt)
        prompt = (
            f"{tags['system_start']}{full_system}{tags['system_end']}"
            f"{history_str}"
            f"{tags['user_start']}{formatted_prompt}{tags['user_end']}"
            f"{tags['assistant_start']}"
        )

        try:
            with self.lock:
                output = self.llm(prompt, max_tokens=max_tokens, stop=tags['stop'], echo=False)

            text = output['choices'][0]['text']
            # Clean tags
            for t in ["<|im_start|>", "<|im_end|>", "<start_of_turn>", "<end_of_turn>"]:
                text = text.replace(t, "")
            text = self._strip_thinking(text)
            response = text.strip().replace('"', '').replace("Obama:", "")

            self._update_history(user_prompt, response)
            return response
        except Exception as e:
            return f"Thinking error: {e}"

    def generate_response_stream(self, user_prompt: str, max_tokens=120):
        if not self.llm:
            yield "My brain is offline."
            return

        tags = self._get_tags()
        now = datetime.now().strftime('%H:%M')
        base_system = self.dynamic_prompt or config.SYSTEM_PROMPT
        full_system = f"{base_system}\nContext: It is {now}."

        history_str = ""
        if self.memory_enabled:
            with self.lock:
                for msg in self.history:
                    role_start = tags['user_start'] if msg['role'] == 'user' else tags['assistant_start']
                    role_end = tags['user_end'] if msg['role'] == 'user' else tags['assistant_end']
                    history_str += f"{role_start}{msg['content']}{role_end}"

        formatted_prompt = self._format_user_prompt(user_prompt)
        prompt = (
            f"{tags['system_start']}{full_system}{tags['system_end']}"
            f"{history_str}"
            f"{tags['user_start']}{formatted_prompt}{tags['user_end']}"
            f"{tags['assistant_start']}"
        )

        try:
            complete_response = ""
            in_think_block = False
            with self.lock:
                output = self.llm(
                    prompt,
                    max_tokens=max_tokens,
                    stop=tags['stop'],
                    echo=False,
                    stream=True
                )
            
            for chunk in output:
                token = chunk['choices'][0]['text']
                for t in ["<|im_start|>", "<|im_end|>", "<start_of_turn>", "<end_of_turn>"]:
                    token = token.replace(t, "")
                token = token.replace("Obama:", "")
                if token:
                    complete_response += token
                    # Suppress <think> blocks in real-time during streaming
                    if config.LLM_DISABLE_THINKING:
                        if '<think>' in complete_response and not in_think_block:
                            in_think_block = True
                        if in_think_block:
                            if '</think>' in complete_response:
                                in_think_block = False
                                # Strip all think blocks and yield the clean remainder
                                clean = self._strip_thinking(complete_response)
                                complete_response = clean
                            continue
                    yield token

            final = self._strip_thinking(complete_response).strip().replace('"', '')
            self._update_history(user_prompt, final)
        except Exception as e:
            yield f"Thinking error: {e}"

    def generate_response_stream_async(self, user_prompt: str, queue, loop):
        """Runs in a background thread, puts tokens into the queue."""
        try:
            generator = self.generate_response_stream(user_prompt)
            for token in generator:
                loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, f"Thinking error: {e}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)


    def _update_history(self, user, ai):
        # Do not save to history if memory is disabled
        if not self.memory_enabled:
            return

        with self.lock:
            self.history.append({"role": "user", "content": user})
            self.history.append({"role": "assistant", "content": ai})
            if len(self.history) > 20:
                self.history = self.history[-20:]

    def reset_memory(self):
        with self.lock:
            self.history = []

    def undo_last_memory(self):
        """Removes the last interaction (user + assistant) from memory."""
        with self.lock:
            if len(self.history) >= 2:
                # Remove last two messages (user and assistant)
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

    def recommend_song(self, description, chat_context=None):
        """
        Sophisticated recommendation:
        1. Contextual vibe analysis.
        2. LLM seed/track list generation with intent recognition.
        3. iTunes verification & standardization.
        4. History filtering.
        """
        # If LLM is not available, fall back to pure keyword iTunes search
        if not self.llm:
            print("🧠 LLM is offline. Falling back to direct iTunes keyword search.")
            fallback_seeds = [description] if description and description != "random music" else []
            if not fallback_seeds:
                fallback_seeds = ["classic rock", "pop", "electronic", "jazz", "lofi"]
                random.shuffle(fallback_seeds)
            return self.recommender.get_recommendation(fallback_seeds)

        # 1. Prepare Context
        context_str = ""
        if chat_context:
            # Take last 10 transcripts for flavor
            recent = chat_context[-10:]
            context_str = "Recent chat vibe: " + " | ".join([f"{t['user']}: {t['text']}" for t in recent])

        no_think = " /no_think" if config.LLM_DISABLE_THINKING else ""
        
        tags = self._get_tags()
        # 2. Build structured prompt
        prompt = (
            f"{tags['system_start']}"
            f"You are a master music recommender and curator bot.\n"
            f"Your job is to analyze the user's music request, identify the intent and vibe, and return structured recommendations.\n"
            f"Analyze the user request and recent chat context (if provided).\n"
            f"Determine the intent:\n"
            f"- SPECIFIC: The user is asking for a specific artist, song, or album (e.g. 'play Queen', 'play Yesterday').\n"
            f"- GENRE_MOOD: The user is asking for a genre, mood, activity, or era (e.g. 'chill lofi', 'workout music', '80s pop').\n"
            f"- OPEN: The user is asking for a general/random recommendation or didn't specify details.\n\n"
            f"Then, generate a list of 5-7 real, existing songs (Artist - Song Title) that best match this request. "
            f"If the request is SPECIFIC to a song, that exact song MUST be the first recommendation. "
            f"If the request is SPECIFIC to an artist, the recommendations must be their most popular tracks or highly similar songs.\n"
            f"If the request is GENRE_MOOD, recommendations must fit the mood/genre/energy level.\n"
            f"If the request is OPEN, use the recent conversation vibe (if any) to curate something suitable, or suggest a high-quality track from any good genre.\n\n"
            f"Respond strictly in this format, with no thinking blocks or extra conversational text:\n"
            f"[INTENT]\n"
            f"<SPECIFIC, GENRE_MOOD, or OPEN>\n"
            f"[VIBE]\n"
            f"<Brief description of the detected vibe/mood/genre>\n"
            f"[RECOMMENDATIONS]\n"
            f"<Artist 1> - <Song Title 1>\n"
            f"<Artist 2> - <Song Title 2>\n"
            f"<Artist 3> - <Song Title 3>\n"
            f"<Artist 4> - <Song Title 4>\n"
            f"<Artist 5> - <Song Title 5>\n"
            f"{tags['system_end']}"
            f"{tags['user_start']}"
            f"Context: {context_str}\n"
            f"User request: {description}\n"
            f"Generate recommendations.{no_think}\n{tags['user_end']}"
            f"{tags['assistant_start']}"
        )

        try:
            with self.lock:
                output = self.llm(
                    prompt,
                    max_tokens=250,
                    stop=tags['stop'],
                    echo=False,
                    temperature=0.6
                )

            llm_text = self._strip_thinking(output['choices'][0]['text'].strip())
            intent, vibe, recommendations = self.parse_recommendation_output(llm_text)
            
            print(f"🎵 Recommendation Intent: {intent}, Vibe: {vibe}")
            print(f"🎵 LLM Recommendations: {recommendations}")
            
            if not recommendations:
                print("⚠️ LLM didn't return formatted recommendations. Trying fallback keyword search.")
                return self.recommender.get_recommendation([description])

            # Try to find a track from the recommendations
            for i, track in enumerate(recommendations):
                # If intent is SPECIFIC and it's the very first recommendation,
                # we can bypass the history check, because the user explicitly asked for it!
                is_explicit_request = (intent == "SPECIFIC" and i == 0)
                
                if not is_explicit_request and self.recommender.is_in_history(track):
                    continue
                
                # Verify and clean the song name via iTunes Search API (optional but good)
                verified = self.recommender.verify_track_on_itunes(track)
                final_track = verified if verified else track
                
                # Check again if the verified name is in history
                if not is_explicit_request and self.recommender.is_in_history(final_track):
                    continue
                
                # Save to history and return
                self.recommender.add_to_history(final_track)
                return final_track

            # If all were in history or verification filtered everything, return the first one as fallback
            fallback_track = recommendations[0]
            verified = self.recommender.verify_track_on_itunes(fallback_track)
            final_track = verified if verified else fallback_track
            self.recommender.add_to_history(final_track)
            return final_track

        except Exception as e:
            print(f"Recommendation error: {e}. Trying fallback keyword search.")
            return self.recommender.get_recommendation([description])



    # --- NEW METHOD ---
    def generate_hourly_report(self, active_users, recent_transcripts):
        if not self.llm: return None

        now = datetime.now().strftime('%H:%M')

        # Format recent transcripts for context
        transcript_text = ""
        if recent_transcripts:
            transcript_text = "\n".join([f"- {t['user']}: {t['text']}" for t in recent_transcripts])
        else:
            transcript_text = "No one has spoken recently."

        users_text = ", ".join(active_users) if active_users else "No one else is here."
        no_think = " /no_think" if config.LLM_DISABLE_THINKING else ""

        tags = self._get_tags()
        prompt = (
            f"{tags['system_start']}"
            f"{config.SYSTEM_PROMPT} "
            f"It is currently {now}. You are giving a periodic hourly status update to the room. "
            f"Mention the current time, acknowledge who is in the room ({users_text}), "
            f"and briefly summarize or comment on the vibe based on the last minute of conversation if any.\n"
            f"Keep it brief (under 4 sentences), witty, and butler-like.\n{tags['system_end']}"
            f"{tags['user_start']}"
            f"Recent conversation:\n{transcript_text}\n\nGive the status update.{no_think}\n{tags['user_end']}"
            f"{tags['assistant_start']}"
        )

        try:
            with self.lock:
                output = self.llm(
                    prompt,
                    max_tokens=350,
                    stop=tags['stop'],
                    echo=False
                )
            return self._strip_thinking(output['choices'][0]['text'].strip().replace('"', ''))
        except Exception as e:
            print(f"Report generation error: {e}")
            return f"It is {now}. I am unable to assess the situation due to a processing error."


