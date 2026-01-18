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

    def generate_response(self, user_prompt: str, max_tokens=150) -> str:
        if not self.llm: return "My brain is offline."

        now = datetime.now().strftime('%H:%M')
        # Using the prompt from config
        full_system = f"{config.SYSTEM_PROMPT}\nContext: It is {now}."

        history_str = ""
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
                output = self.llm(prompt, max_tokens=max_tokens, stop=["<|im_end|>", "\n"], echo=False)

            response = output['choices'][0]['text'].strip().replace('"', '').replace("Obama:", "")
            self._update_history(user_prompt, response)
            return response
        except Exception as e:
            return f"Thinking error: {e}"

    def _update_history(self, user, ai):
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
            f"<|im_start|>system\nYou are a DJ. Output ONE search query (Artist - Title).\n<|im_end|>\n"
            f"<|im_start|>user\nRecommend: {description}\n<|im_end|>\n<|im_start|>assistant\n"
        )
        try:
            with self.lock:
                output = self.llm(prompt, max_tokens=50, stop=["<|im_end|>", "\n"], echo=False)
            return output['choices'][0]['text'].strip().replace('"', '')
        except: return None
