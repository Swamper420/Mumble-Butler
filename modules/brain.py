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

        # Initialize settings from config
        self.memory_enabled = getattr(config, 'MEMORY_ENABLED', False)
        self.api_memory_enabled = getattr(config, 'LLM_API_MEMORY_ENABLED', False)
        self.prompt_format = getattr(config, 'LLM_PROMPT_FORMAT', 'chatml')
        self.disable_thinking = getattr(config, 'LLM_DISABLE_THINKING', True)
        self.dynamic_prompt = None

        if LLM_AVAILABLE:
            try:
                print(f"🧠 Loading LLM ({config.LLM_MODEL_PATH})...")
                # Use official chat_format for the specific model architecture
                chat_format = "gemma" if self.prompt_format == "gemma" else "chatml"
                
                self.llm = Llama(
                    model_path=config.LLM_MODEL_PATH,
                    n_ctx=config.LLM_CONTEXT_SIZE,
                    n_gpu_layers=config.LLM_GPU_LAYERS,
                    verbose=False,
                    chat_format=chat_format
                )
            except Exception as e:
                print(f"❌ LLM Error: {e}")

    def _get_stop_tokens(self):
        """Returns standard stop tokens for the current format."""
        if self.prompt_format == "gemma":
            return ["<end_of_turn>", "<start_of_turn>", "<thought>", "</thought>"]
        return ["<|im_end|>", "<|im_start|>", "<thought>", "</thought>"]

    def _clean_response(self, text):
        """
        Refined sanitizer. Only strips metadata/tags, never common words.
        """
        import re
        
        # 1. Strip thought blocks (the 'snappy' requirement)
        text = re.sub(r'<(thought|reasoning)>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<(thought|reasoning)>.*', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # 2. Strip only structural tags, not content words
        structural_tags = ["<|im_start|>", "<|im_end|>", "<start_of_turn>", "<end_of_turn>"]
        for tag in structural_tags:
            text = text.replace(tag, "")
        
        # 3. Clean common chat-format artifacts (only at the very start)
        text = re.sub(r'^(assistant|model|user|system|obama|butler)[:\s]+', '', text, flags=re.IGNORECASE)
        
        return text.strip().replace('"', '')

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
        
        # Add snappy directive
        if self.disable_thinking:
            base_system += " Respond directly. No thinking blocks."
            
        full_system = f"{base_system}\nContext: It is {now}."

        messages = [{"role": "system", "content": full_system}]
        if self.memory_enabled:
            with self.lock:
                messages.extend(self.history)
        messages.append({"role": "user", "content": user_prompt})

        try:
            with self.lock:
                output = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    stop=self._get_stop_tokens()
                )

            text = output['choices'][0]['message']['content']
            response = self._clean_response(text)

            self._update_history(user_prompt, response)
            return response
        except Exception as e:
            return f"Brain error: {e}"

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
            if self.disable_thinking:
                api_system += " No thinking blocks."
            full_system = f"{api_system}\nContext: It is {now}."

            messages = [{"role": "system", "content": full_system}]
            if self.api_memory_enabled:
                with self.lock:
                    messages.extend(self.api_history)
            messages.append({"role": "user", "content": user_prompt})

            try:
                with self.lock:
                    output = self.llm.create_chat_completion(
                        messages=messages,
                        max_tokens=max_tokens,
                        stop=self._get_stop_tokens()
                    )

                text = output['choices'][0]['message']['content']
                response = self._clean_response(text)

                if self.api_memory_enabled:
                    with self.lock:
                        self.api_history.append({"role": "user", "content": user_prompt})
                        self.api_history.append({"role": "assistant", "content": response})
                        if len(self.api_history) > 10:
                            self.api_history = self.api_history[-10:]

                return response
            except Exception as e:
                return f"Brain error: {e}"

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
        system = (
            "You are a master music curator. prioritized user artists. "
            "Generate 5 search terms separated by commas. No thinking blocks."
        )
        user = f"Context: {context_str}\nUser request: {description}"
        
        try:
            with self.lock:
                output = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    max_tokens=60,
                    stop=self._get_stop_tokens() + ["\n"],
                    temperature=0.7
                )
            
            seed_text = output['choices'][0]['message']['content'].strip()
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

        system = (
            f"{config.SYSTEM_PROMPT} "
            f"Hourly update for {now}. Room: {users_text}. No thinking."
        )
        user = f"Recent conversation:\n{transcript_text}"
        
        try:
            with self.lock:
                output = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    max_tokens=350,
                    stop=self._get_stop_tokens() + ["\n"]
                )
            return self._clean_response(output['choices'][0]['message']['content'])
        except Exception as e:
            print(f"Report generation error: {e}")
            return f"It is {now}. I am unable to assess the situation due to a processing error."

    def generate_kill_commentary(self, kills: list) -> str:
        """
        Generates short, entertaining CS2 kill-feed commentary.
        `kills` is a list of kill-event dicts produced by CS2GSI.
        Handles single kills through aces in one call.
        """
        if not self.llm:
            return ""

        count = len(kills)
        # Build a readable summary of what happened
        lines = []
        for k in kills:
            killer = k.get('killer', 'Someone')
            victim = k.get('victim') or ''
            weapon = k.get('weapon', 'their weapon')
            hs = k.get('headshot', False)
            victim_part = f" killing {victim}" if victim else ""
            hs_part = " (headshot)" if hs else ""
            lines.append(f"{killer} got a kill with {weapon}{victim_part}{hs_part}")

        kill_text = "\n".join(lines)

        multi_label = {
            1: "a kill",
            2: "a double kill",
            3: "a triple kill",
            4: "a quadruple kill",
        }.get(count, "an ACE" if count >= 5 else f"{count} kills")

        system = (
            f"{config.SYSTEM_PROMPT} "
            f"Watching CS2 match. React to {multi_label}. No thinking."
        )
        user = f"Kill feed:\n{kill_text}"
        
        try:
            with self.lock:
                output = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    max_tokens=80,
                    stop=self._get_stop_tokens(),
                    temperature=0.85,
                )
            return self._clean_response(output['choices'][0]['message']['content'])
        except Exception as e:
            print(f"Kill commentary error: {e}")
            return ""

    def generate_round_report(self, report: dict) -> str:
        """
        Generates an end-of-round economic and performance report.
        `report` is the dict produced by CS2GSI._fire_round_end.
        """
        if not self.llm:
            return ""

        win_team = report.get('win_team', 'unknown')
        condition = report.get('win_condition', '')
        ct_score = report.get('ct_score', 0)
        t_score = report.get('t_score', 0)
        map_name = report.get('map', 'unknown')
        round_num = report.get('round_number', 0)
        players = report.get('players', [])

        # Build compact player table
        player_lines = []
        for p in sorted(players, key=lambda x: x.get('kills', 0), reverse=True):
            name = p.get('name', '?')
            team = p.get('team', '?')
            kda = f"{p.get('kills',0)}/{p.get('deaths',0)}/{p.get('assists',0)}"
            eco = p.get('eco_label', '?')
            money = p.get('money', 0)
            player_lines.append(f"  {name} [{team}] KDA:{kda} eco:{eco} ${money:,}")

        player_text = "\n".join(player_lines) if player_lines else "No player data."

        local_team = report.get('local_team', '')
        streak = report.get('streak', 0)
        streak_team = report.get('streak_team', '')

        # Build dynamic context about how we are doing
        context_str = ""
        if local_team:
            if streak >= 3 and streak_team != local_team:
                context_str = f"Your team ({local_team}) is losing badly (the enemy {streak_team} is on a {streak} round win streak). Be HIGHLY sarcastic, cynical, and brutally mock your team's terrible performance."
            elif streak_team == local_team and streak >= 2:
                context_str = f"Your team ({local_team}) is on a {streak} round win streak! Hype them up enthusiastically!"
            elif win_team == local_team:
                context_str = f"Your team ({local_team}) won the round! Hype them up!"
            else:
                context_str = f"Your team ({local_team}) lost the round. Give a sarcastic remark about their performance."
        else:
            context_str = "Comment on the winner and economy neutrally."

        system = (
            f"{config.SYSTEM_PROMPT} "
            f"CS2 post-round debrief. Winner: {win_team}. No thinking."
        )
        user = f"Score: CT {ct_score} - T {t_score}\nStats:\n{player_text}"
        
        try:
            with self.lock:
                output = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    max_tokens=150,
                    stop=self._get_stop_tokens(),
                    temperature=0.75,
                )
            return self._clean_response(output['choices'][0]['message']['content'])
        except Exception as e:
            print(f"Round report error: {e}")
            return ""
