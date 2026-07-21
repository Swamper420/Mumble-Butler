import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# --- CONNECTION ---
SERVER_IP = os.getenv("MUMBLE_SERVER_IP", "127.0.0.1")
SERVER_PORT = int(os.getenv("MUMBLE_SERVER_PORT", "64738"))
BOT_USERNAME = os.getenv("MUMBLE_BOT_USERNAME", "Obama")
PASSWORD = os.getenv("MUMBLE_PASSWORD", "")
TARGET_CHANNEL = os.getenv("MUMBLE_TARGET_CHANNEL", "General")
IGNORED_USERS = os.getenv("MUMBLE_IGNORED_USERS", "YoMusicBot").split(",")
RECONNECT_DELAY = int(os.getenv("MUMBLE_RECONNECT_DELAY", "5"))



# --- PATHS ---
STATS_FILE = os.getenv("STATS_FILE", "user_stats.csv")
CHIME_FILE = os.getenv("CHIME_FILE", "chime.wav")

# --- OLLAMA / LLM CONFIG ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4-e2b")
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "models/gemma-3-8b-it-q4_k_m.gguf")
LLM_PROMPT_FORMAT = os.getenv("LLM_PROMPT_FORMAT", "gemma") # "gemma" or "chatml"
LLM_DISABLE_THINKING = os.getenv("LLM_DISABLE_THINKING", "True").lower() == "true"
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
OLLAMA_THINK_BUFFER = int(os.getenv("OLLAMA_THINK_BUFFER", "1024"))


# --- AI CONFIG ---
MOONSHINE_MODEL_SIZE = os.getenv("MOONSHINE_MODEL_SIZE", "UsefulSensors/moonshine-streaming-medium")
MOONSHINE_DEVICE = os.getenv("MOONSHINE_DEVICE", "cuda")


LLM_CONTEXT_SIZE = int(os.getenv("LLM_CONTEXT_SIZE", "2000"))
LLM_GPU_LAYERS = int(os.getenv("LLM_GPU_LAYERS", "-1"))
ACTIVATION_KEYWORDS = os.getenv("ACTIVATION_KEYWORDS", "obama,opama,opal,opa").split(",")
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "True").lower() == "true"

# --- WAKEWORD CONFIG ---
WAKEWORD_LIBRARY = os.getenv("WAKEWORD_LIBRARY", "openwakeword")
WAKEWORD_MODEL_PATHS = [p.strip() for p in os.getenv("WAKEWORD_MODEL_PATHS", "").split(",") if p.strip()]
WAKEWORD_BUILTIN_MODELS = [m.strip() for m in os.getenv("WAKEWORD_BUILTIN_MODELS", "hey_jarvis").split(",") if m.strip()]
WAKEWORD_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", "0.5"))

TTS_ENGINE = os.getenv("TTS_ENGINE", "chatterbox-turbo")

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", (
    "You are 'Obama', a suave and savvy digital butler from the 2000s. "
    "You are impeccable, polite, and efficiently helpful. "
    "Keep your responses short and concise — ideally one or two sentences. "
    "Always respond in ENGLISH."
    + (" You are encouraged to use expressive paralinguistic tags like [laugh], [sigh], [gasp], [cough], [chuckle] in your responses to sound natural." if TTS_ENGINE == "chatterbox-turbo" else "")
))

SHUTUP_KEYWORDS = os.getenv("SHUTUP_KEYWORDS", "shut up,shutup,be quiet").split(",")

KOKORO_VOICE_ID = os.getenv("KOKORO_VOICE_ID", 'am_michael')
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "0.9"))

CHATTERBOX_VOICE_DIR = os.getenv("CHATTERBOX_VOICE_DIR", "data/voices")
CHATTERBOX_DEFAULT_VOICE = os.getenv("CHATTERBOX_DEFAULT_VOICE", "michael")
CHATTERBOX_TEMPERATURE = float(os.getenv("CHATTERBOX_TEMPERATURE", "0.8"))

AVAILABLE_VOICES = {
    'heart': 'af_heart', 'bella': 'af_bella', 'nicole': 'af_nicole',
    'michael': 'am_michael', 'emma': 'bf_emma', 'george': 'bm_george',
    'alpha': 'jf_alpha', 'siwis': 'ff_siwis', 'alpha2': 'hf_alpha',
    'sara': 'if_sara'
}

# --- VOICE COMMAND TRIGGERS ---
VOICE_TRIGGERS = {
    'FORGET': ["forget"],
    'VOLUME': ["volume"],
    'PLAY_MUSIC': ["music"],
    'PLAY_SPECIFIC': ["play", "queue"],
    'RECOMMEND': ["recommend"],
    'STOP': ["stop", "silence"],
    'SKIP': ["skip", "next"],
    'PLAY_FILE': ["file"],
    'REPEAT': ["repeat"],
    'MODE': ["mode"],
    'REMIND': ["remind"],
    'STATUS': ["status"],
    'PING': ["ping", "are you there"]
}

# --- BOTAMUSIQUE COMMANDS ---
MUMBLE_COMMANDS = {
    'VOLUME': "!volume",
    'PLAY_GENERIC': "!play",
    'PLAY_YOUTUBE': "!yplay",
    'PAUSE': "!pause",
    'STOP': "!stop",
    'SKIP': "!skip",
    'FILE': "!file",
    'REPEAT': "!repeat",
    'MODE': "!mode",
    'NOW_PLAYING': "!np",
    'NOW_PLAYING_INFO': "!np -v",
    'QUEUE': "!queue",
    'CLEAR': "!clear"
}

# --- TEXT CHAT TRIGGERS ---
TEXT_TRIGGERS = {
    'HELP': "?help",
    'STATUS': "?status",
    'LISTEN': "?listen",
    'FORGET': "?forget",
    'VOICE': "?voice",
    'SAY': "?say",
    'SAYSAVE': "?saysave",
    'MEMORY': "?memory",
    'RECOMMEND': "?recommend",
    'REMIND': "?remind"
}

# --- AUDIO PARAMETERS ---
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.5"))
MIN_AUDIO_LENGTH = float(os.getenv("MIN_AUDIO_LENGTH", "0.3"))
POLL_RATE = float(os.getenv("POLL_RATE", "0.1"))

# --- RECOMMENDATION SYSTEM ---
MUSIC_HISTORY_FILE = os.getenv("MUSIC_HISTORY_FILE", "data/music_history.json")
RECOMMENDER_MAX_HISTORY = int(os.getenv("RECOMMENDER_MAX_HISTORY", "50"))


