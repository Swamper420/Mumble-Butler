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

# --- WEB SERVER ---
WEB_SERVER_ENABLED = os.getenv("WEB_SERVER_ENABLED", "True").lower() == "true"
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "8080"))




# --- PATHS ---
STATS_FILE = os.getenv("STATS_FILE", "user_stats.csv")
CHIME_FILE = os.getenv("CHIME_FILE", "chime.wav")

# --- OLLAMA / LLM CONFIG ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4-e2b")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "15m")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))
OLLAMA_CONNECT_TIMEOUT = int(os.getenv("OLLAMA_CONNECT_TIMEOUT", "3"))
LLM_PROMPT_FORMAT = os.getenv("LLM_PROMPT_FORMAT", "gemma") # "gemma" or "chatml"
LLM_DISABLE_THINKING = os.getenv("LLM_DISABLE_THINKING", "True").lower() == "true"
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_CONTEXT_SIZE = int(os.getenv("LLM_CONTEXT_SIZE", "2048"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_HISTORY = int(os.getenv("LLM_MAX_HISTORY", "20"))
OLLAMA_THINK_BUFFER = int(os.getenv("OLLAMA_THINK_BUFFER", "1024"))
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "True").lower() == "true"
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3"))


# --- AI CONFIG ---
MOONSHINE_MODEL_SIZE = os.getenv("MOONSHINE_MODEL_SIZE", "UsefulSensors/moonshine-streaming-small")
MOONSHINE_DEVICE = os.getenv("MOONSHINE_DEVICE", "cuda")


ACTIVATION_KEYWORDS = os.getenv("ACTIVATION_KEYWORDS", "obama,opama,opal,opa").split(",")
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "True").lower() == "true"

# --- WAKEWORD CONFIG ---
WAKEWORD_LIBRARY = os.getenv("WAKEWORD_LIBRARY", "openwakeword")
WAKEWORD_MODEL_PATHS = [p.strip() for p in os.getenv("WAKEWORD_MODEL_PATHS", "").split(",") if p.strip()]
WAKEWORD_BUILTIN_MODELS = [m.strip() for m in os.getenv("WAKEWORD_BUILTIN_MODELS", "hey_jarvis").split(",") if m.strip()]
WAKEWORD_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", "0.5"))
WAKEWORD_CONSECUTIVE_HITS = int(os.getenv("WAKEWORD_CONSECUTIVE_HITS", "2"))

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", (
    "You are 'Obama', a suave and savvy digital butler from the 2000s. "
    "You are impeccable, polite, and efficiently helpful. "
    "Keep your responses short and concise — ideally one or two sentences. "
    "Always respond in ENGLISH. "
    "You are encouraged to use expressive paralinguistic tags like [laugh], [sigh], [gasp], [cough], [chuckle] in your responses to sound natural."
))

SHUTUP_KEYWORDS = os.getenv("SHUTUP_KEYWORDS", "shut up,shutup,be quiet").split(",")

CHATTERBOX_MODEL = os.getenv("CHATTERBOX_MODEL", "nano") # "nano", "turbo", "standard", "multilingual", "https://huggingface.co/Finnish-NLP/Chatterbox-Finnish"
CHATTERBOX_API_MODEL = os.getenv("CHATTERBOX_API_MODEL", "https://huggingface.co/Finnish-NLP/Chatterbox-Finnish")
CHATTERBOX_API_FORMAT = os.getenv("CHATTERBOX_API_FORMAT", "ogg") # "ogg", "wav", "pcm", "json"
CHATTERBOX_VOICE_DIR = os.getenv("CHATTERBOX_VOICE_DIR", "data/voices")
CHATTERBOX_DEFAULT_VOICE = os.getenv("CHATTERBOX_DEFAULT_VOICE", "michael")

CHATTERBOX_LANGUAGE = os.getenv("CHATTERBOX_LANGUAGE", "fi")
CHATTERBOX_TEMPERATURE = float(os.getenv("CHATTERBOX_TEMPERATURE", "0.8"))
CHATTERBOX_REPETITION_PENALTY = float(os.getenv("CHATTERBOX_REPETITION_PENALTY", "1.2"))
CHATTERBOX_EXAGGERATION = float(os.getenv("CHATTERBOX_EXAGGERATION", "0.6"))
CHATTERBOX_VOICE_CACHE_LIMIT = int(os.getenv("CHATTERBOX_VOICE_CACHE_LIMIT", "1"))





# --- FAST PRECACHED AUDIO RESPONSES (EXPERIMENTAL) ---
FAST_AUDIO_RESPONSES_ENABLED = os.getenv("FAST_AUDIO_RESPONSES_ENABLED", "False").lower() == "true"
FAST_AUDIO_CACHE_DIR = os.getenv("FAST_AUDIO_CACHE_DIR", "data/precached_audio")
FAST_WAKEWORD_RESPONSES = [
    p.strip() for p in os.getenv("FAST_WAKEWORD_RESPONSES", "Yes?, [chuckle], Listening..., Mm?, Sir?, Yo").split(",") if p.strip()
]
FAST_ACTION_CONFIRMATIONS = {
    "MUSIC": os.getenv("FAST_ACTION_MUSIC", "Fetching song..."),
    "SEARCH": os.getenv("FAST_ACTION_SEARCH", "Searching up to date information..."),
    "THINK": os.getenv("FAST_ACTION_THINK", "Let me see..."),
    "MEMORY": os.getenv("FAST_ACTION_MEMORY", "Wiping memory..."),
    "STOP": os.getenv("FAST_ACTION_STOP", "Stopping..."),
    "VOLUME": os.getenv("FAST_ACTION_VOLUME", "Adjusting volume..."),
    "MODE": os.getenv("FAST_ACTION_MODE", "Changing mode..."),
    "SKIP": os.getenv("FAST_ACTION_SKIP", "Skipping..."),
    "RESUME": os.getenv("FAST_ACTION_RESUME", "Resuming..."),
    "FILE": os.getenv("FAST_ACTION_FILE", "Playing file..."),
    "REPEAT": os.getenv("FAST_ACTION_REPEAT", "Setting repeat..."),
    "REMIND": os.getenv("FAST_ACTION_REMIND", "Setting reminder..."),
    "STATUS": os.getenv("FAST_ACTION_STATUS", "Checking status..."),
    "PING": os.getenv("FAST_ACTION_PING", "Checking in..."),
}

# --- VOICE COMMAND TRIGGERS ---
VOICE_TRIGGERS = {
    'FORGET': ["forget"],
    'VOLUME': ["volume"],
    'PLAY_MUSIC': ["music"],
    'PLAY_SPECIFIC': ["play", "queue"],
    'RECOMMEND': ["recommend"],
    'SEARCH': ["search", "google", "look up"],
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
    'REMIND': "?remind",
    'SEARCH': "?search"
}

# --- AUDIO PARAMETERS ---
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.5"))
SILENCE_TRIM_THRESHOLD = float(os.getenv("SILENCE_TRIM_THRESHOLD", "0.001"))
MIN_AUDIO_LENGTH = float(os.getenv("MIN_AUDIO_LENGTH", "0.3"))
MAX_AUDIO_BUFFER_SECONDS = float(os.getenv("MAX_AUDIO_BUFFER_SECONDS", "10.0"))
POLL_RATE = float(os.getenv("POLL_RATE", "0.1"))
SAYSAVE_SAVE_DIR = os.getenv("SAYSAVE_SAVE_DIR", "data/saysaves")
HOURLY_REPORT_ENABLED = os.getenv("HOURLY_REPORT_ENABLED", "True").lower() == "true"

# --- RECOMMENDATION SYSTEM ---
MUSIC_HISTORY_FILE = os.getenv("MUSIC_HISTORY_FILE", "data/music_history.json")
RECOMMENDER_MAX_HISTORY = int(os.getenv("RECOMMENDER_MAX_HISTORY", "50"))
RECOMMENDER_ITUNES_LIMIT = int(os.getenv("RECOMMENDER_ITUNES_LIMIT", "3"))
RECOMMENDER_ITUNES_TIMEOUT = int(os.getenv("RECOMMENDER_ITUNES_TIMEOUT", "5"))


