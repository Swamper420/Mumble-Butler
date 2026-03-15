import threading
from datetime import datetime
import random
import config

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

        # Initialize memory state from config (defaults to False if not set)
        self.memory_enabled = getattr(config, 'MEMORY_ENABLED', False)

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

    def generate_response(self, user_prompt: str, max_tokens=650) -> str:
        if not self.llm: return "My brain is offline."

        now = datetime.now().strftime('%H:%M')
        full_system = f"{config.SYSTEM_PROMPT}\nContext: It is {now}."

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

    def recommend_song(self, description):
            if not self.llm: return None

            # 1. Define a list of dynamic DJ personas to ensure variety
            dj_personas = [
                "You are an underground DJ who loves obscure, underrated gems. Avoid mainstream top 40.",
                "You are a music historian looking for timeless classics that people often forget.",
                "You are a trend-setter looking for the absolute freshest, most unique sounds from the last few years.",
                "You are an eclectic curator who mixes genres unexpectedly. Surprise the user.",
                "You are a 'crate digger' looking for rare vinyl cuts and b-sides."
            ]

            # 2. Pick a random persona
            current_persona = random.choice(dj_personas)

            # 3. Construct the prompt with positive constraints
            # We explicitly ask for "Artist - Title" format.
            prompt = (
                f"<|im_start|>system\n{current_persona} "
                f"Your task is to recommend a song based on the user's vibe. "
                f"Output ONLY ONE search query in the format 'Artist - Title'. Do not output any other text.\n<|im_end|>\n"
                f"<|im_start|>user\nRecommend a song for this vibe: {description}\n<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

            try:
                with self.lock:
                    # 4. Increase temperature to 0.85 (default is usually lower) for more creativity
                    output = self.llm(
                        prompt,
                        max_tokens=90,
                        stop=["<|im_end|>", "\n"],
                        echo=False,
                        temperature=0.90,  # Higher temp = more "unique" / "fresh" choices
                        top_p=0.95         # Nucleus sampling for quality
                    )

                result = output['choices'][0]['text'].strip().replace('"', '')
                print(f"🎵 Recommendation [{current_persona}]: {result}") # Debug log
                return result
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
