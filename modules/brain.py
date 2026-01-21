import threading
from datetime import datetime
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
                output = self.llm(prompt, max_tokens=max_tokens, stop=["<|im_end|>", "<|im_start|>", "\n"], echo=False)

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
        prompt = (
            f"<|im_start|>system\nYou are a fancy DJ who dislikes Daft Punk and DJ Snake. Output ONLY ONE search query (Artist - Title), nothing else.\n<|im_end|>\n"
            f"<|im_start|>user\nRecommend: {description}\n<|im_end|>\n<|im_start|>assistant\n"
        )
        try:
            with self.lock:
                output = self.llm(prompt, max_tokens=90, stop=["<|im_end|>", "\n"], echo=False)
            return output['choices'][0]['text'].strip().replace('"', '')
        except: return None
