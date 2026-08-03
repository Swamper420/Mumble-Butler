import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- CONNECTION ---
SERVER_IP = os.getenv("MUMBLE_SERVER_IP", "127.0.0.1")
SERVER_PORT = int(os.getenv("MUMBLE_SERVER_PORT", "64738"))
BOT_USERNAME = os.getenv("MUMBLE_BOT_USERNAME", "Obama")
PASSWORD = os.getenv("MUMBLE_PASSWORD", "")
TARGET_CHANNEL = os.getenv("MUMBLE_TARGET_CHANNEL", "General")
IGNORED_USERS = os.getenv("MUMBLE_IGNORED_USERS", "YoMusicBot").split(",")
RECONNECT_DELAY = int(os.getenv("MUMBLE_RECONNECT_DELAY", "5"))

# --- PATHS ---
CHIME_FILE = os.getenv("CHIME_FILE", "chime.wav")

# --- OLLAMA / LLM CONFIG ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4-e2b")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "15m")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))
OLLAMA_CONNECT_TIMEOUT = int(os.getenv("OLLAMA_CONNECT_TIMEOUT", "3"))
LLM_DISABLE_THINKING = os.getenv("LLM_DISABLE_THINKING", "True").lower() == "true"
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_CONTEXT_SIZE = int(os.getenv("LLM_CONTEXT_SIZE", "2048"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_HISTORY = int(os.getenv("LLM_MAX_HISTORY", "20"))
OLLAMA_THINK_BUFFER = int(os.getenv("OLLAMA_THINK_BUFFER", "1024"))
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "True").lower() == "true"
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3"))


# --- STT API CONFIG ---
STT_API_URL = os.getenv("STT_API_URL", "http://localhost:8001")
STT_BEAM_SIZE = int(os.getenv("STT_BEAM_SIZE", "5"))
STT_VAD_FILTER = os.getenv("STT_VAD_FILTER", "True").lower() == "true"
STT_WORD_TIMESTAMPS = os.getenv("STT_WORD_TIMESTAMPS", "False").lower() == "true"
STT_INITIAL_PROMPT = os.getenv("STT_INITIAL_PROMPT", "")
STT_TIMEOUT = int(os.getenv("STT_TIMEOUT", "15"))


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
))

SHUTUP_KEYWORDS = os.getenv("SHUTUP_KEYWORDS", "shut up,shutup,be quiet").split(",")

# --- TTS API CONFIG ---
TTS_API_URL = os.getenv("TTS_API_URL", "http://localhost:8000")
TTS_MODEL = os.getenv("TTS_MODEL", "omnivoice")
TTS_VOICE = os.getenv("TTS_VOICE", "mieto_fi")
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "fi")
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))
TTS_NUM_STEP = int(os.getenv("TTS_NUM_STEP", "32"))
TTS_GUIDANCE_SCALE = float(os.getenv("TTS_GUIDANCE_SCALE", "2.0"))
TTS_RESPONSE_FORMAT = os.getenv("TTS_RESPONSE_FORMAT", "wav")
TTS_SEED = int(os.getenv("TTS_SEED", "42"))
TTS_TIMEOUT = int(os.getenv("TTS_TIMEOUT", "30"))






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


