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
        self.api_history = []
        self.recommender = MusicRecommender()

        # Initialize memory state from config (defaults to False if not set)
        self.memory_enabled = getattr(config, 'MEMORY_ENABLED', False)
        self.api_memory_enabled = getattr(config, 'LLM_API_MEMORY_ENABLED', False)
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

    def reset_api_memory(self):
        with self.lock:
            self.api_history = []

    def generate_response(self, user_prompt: str, max_tokens=120, personality_prompt: str = None) -> str:
        if not self.llm: return "My brain is offline."

        now = datetime.now().strftime('%H:%M')
        base_system = self.dynamic_prompt or personality_prompt or config.SYSTEM_PROMPT
        full_system = f"{base_system}\nContext: It is {now}."

        history_str = ""
        # Only include history if memory is enabled
        if self.memory_enabled:
            with self.lock:
                for msg in self.history:
                    history_str += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"

        prompt = (
            f"<|im_start|>system\n{full_system}<|im_end|>\n"
            f"{history_str}"
            f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        try:
            with self.lock:
                output = self.llm(prompt, max_tokens=max_tokens, stop=["<|im_end|>", "<|im_start|>"], echo=False)

            text = output['choices'][0]['text']
            # Clean tags
            text = text.replace("<|im_start|>", "").replace("<|im_end|>", "")
            response = text.strip().replace('"', '').replace("Obama:", "")

            self._update_history(user_prompt, response)
            return response
        except Exception as e:
            return f"Thinking error: {e}"

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

    def generate_api_response(self, user_prompt: str, max_tokens=200) -> str:
            """Generate a long-form response intended for the HTTP API."""
            if not self.llm:
                return "My brain is offline."

            now = datetime.now().strftime('%H:%M')
            api_system = getattr(config, 'API_SYSTEM_PROMPT', config.SYSTEM_PROMPT)
            full_system = f"{api_system}\nContext: It is {now}."

            # 1. Build API history string
            history_str = ""
            if self.api_memory_enabled:
                with self.lock:
                    for msg in self.api_history:
                        history_str += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"

            prompt = (
                f"<|im_start|>system\n{full_system}<|im_end|>\n"
                f"{history_str}"
                f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

            try:
                with self.lock:
                    output = self.llm(prompt, max_tokens=max_tokens, stop=["<|im_end|>", "<|im_start|>"], echo=False)

                text = output['choices'][0]['text']
                text = text.replace("<|im_start|>", "").replace("<|im_end|>", "")
                response = text.strip().replace('"', '').replace("Obama:", "")

                # 2. Update API history
                if self.api_memory_enabled:
                    with self.lock:
                        self.api_history.append({"role": "user", "content": user_prompt})
                        self.api_history.append({"role": "assistant", "content": response})
                        # Keep API history slightly shorter (10 messages) to account for longer max_tokens
                        if len(self.api_history) > 10:
                            self.api_history = self.api_history[-10:]

                return response
            except Exception as e:
                return f"Thinking error: {e}"

    def recommend_song(self, description, chat_context=None):
        """
        Sophisticated recommendation:
        1. Contextual vibe analysis.
        2. LLM seed generation.
        3. External discovery (iTunes).
        """
        if not self.llm:
            return None

        # 1. Prepare Context
        context_str = ""
        if chat_context:
            # Take last 10 transcripts for flavor
            recent = chat_context[-10:]
            context_str = "Recent chat vibe: " + " | ".join([f"{t['user']}: {t['text']}" for t in recent])

        # 2. Generate Seeds
        # We ask for a list of seeds. We emphasize sticking to the user's request if it's specific.
        prompt = (
            f"<|im_start|>system\n"
            f"You are a master music curator. If the user asks for a specific artist, genre, or vibe, "
            f"you MUST prioritize it. Generate a list of 5 search terms. "
            f"If the request is specific (e.g. 'Play Queen'), the terms must be that artist and 4 very similar ones. "
            f"If the request is vague, be more creative. "
            f"Output ONLY the terms separated by commas.\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"Context: {context_str}\n"
            f"User request: {description}\n"
            f"Give me 5 music seeds.\n<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        try:
            with self.lock:
                output = self.llm(
                    prompt,
                    max_tokens=60,
                    stop=["<|im_end|>", "\n"],
                    echo=False,
                    temperature=0.7
                )
            
            seed_text = output['choices'][0]['text'].strip()
            llm_seeds = [s.strip() for s in seed_text.split(',') if s.strip()]
            
            # Final seed list: [User's original request] + [LLM's similar/diverse seeds]
            seeds = []
            if description and description != "random music":
                seeds.append(description)
            
            # Add LLM seeds, avoiding duplicates
            for s in llm_seeds:
                if s.lower() not in [x.lower() for x in seeds]:
                    seeds.append(s)

            print(f"🎵 Final prioritized seeds: {seeds}")

            # 3. Discover
            result = self.recommender.get_recommendation(seeds)
            if result:
                print(f"✅ Recommendation: {result}")
                return result
            
            return None
        except Exception as e:
            print(f"Recommendation error: {e}")
            return None


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

        prompt = (
            f"<|im_start|>system\n"
            f"{config.SYSTEM_PROMPT} "
            f"It is currently {now}. You are giving a periodic hourly status update to the room. "
            f"Mention the current time, acknowledge who is in the room ({users_text}), "
            f"and briefly summarize or comment on the vibe based on the last minute of conversation if any.\n"
            f"Keep it brief (under 4 sentences), witty, and butler-like.\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"Recent conversation:\n{transcript_text}\n\nGive the status update.\n<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        try:
            with self.lock:
                output = self.llm(
                    prompt,
                    max_tokens=350,
                    stop=["<|im_end|>", "\n"],
                    echo=False
                )
            return output['choices'][0]['text'].strip().replace('"', '')
        except Exception as e:
            print(f"Report generation error: {e}")
            return f"It is {now}. I am unable to assess the situation due to a processing error."
