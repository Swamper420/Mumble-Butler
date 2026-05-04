import os
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

JELLYFIN = {
    'BASE_URL': os.getenv("JELLYFIN_BASE_URL", "http://127.0.0.1:8096"),
    'USERNAME': os.getenv("JELLYFIN_USERNAME", ""),
    'PASSWORD': os.getenv("JELLYFIN_PASSWORD", ""),
    'API_KEY': os.getenv("JELLYFIN_API_KEY", ""),
}

# --- PATHS ---
STATS_FILE = os.getenv("STATS_FILE", "user_stats.csv")
CHIME_FILE = os.getenv("CHIME_FILE", "chime.wav")
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "models/gemma-4-9b-it-q4_k_m.gguf")
LLM_PROMPT_FORMAT = os.getenv("LLM_PROMPT_FORMAT", "gemma") # "gemma" or "chatml"
LLM_DISABLE_THINKING = os.getenv("LLM_DISABLE_THINKING", "True").lower() == "true"
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_API_MAX_TOKENS = int(os.getenv("LLM_API_MAX_TOKENS", "2048"))


# --- AI CONFIG ---
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "deepdml/faster-distil-whisper-large-v3.5")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "float16")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "fi")

LLM_CONTEXT_SIZE = int(os.getenv("LLM_CONTEXT_SIZE", "2000"))
LLM_GPU_LAYERS = int(os.getenv("LLM_GPU_LAYERS", "-1"))
ACTIVATION_KEYWORDS = os.getenv("ACTIVATION_KEYWORDS", "obama,opama,opal,opa").split(",")
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "True").lower() == "true"

LLM_API_HOST = os.getenv("LLM_API_HOST", "127.0.0.1")
LLM_API_PORT = int(os.getenv("LLM_API_PORT", "8080"))
LLM_API_DEFAULT_MAX_TOKENS = int(os.getenv("LLM_API_DEFAULT_MAX_TOKENS", "150"))
LLM_API_LOG_REQUESTS = os.getenv("LLM_API_LOG_REQUESTS", "False").lower() == "true"

VOICE_API_HOST = os.getenv("VOICE_API_HOST", "127.0.0.1")
VOICE_API_PORT = int(os.getenv("VOICE_API_PORT", "8081"))
LLM_API_MEMORY_ENABLED = os.getenv("LLM_API_MEMORY_ENABLED", "True").lower() == "true"
VOICE_API_LOG_REQUESTS = os.getenv("VOICE_API_LOG_REQUESTS", "False").lower() == "true"

START_LLM_API_WITH_BOT = os.getenv("START_LLM_API_WITH_BOT", "True").lower() == "true"
START_VOICE_API_WITH_BOT = os.getenv("START_VOICE_API_WITH_BOT", "True").lower() == "true"
API_THREAD_SHUTDOWN_TIMEOUT_SECONDS = int(os.getenv("API_THREAD_SHUTDOWN_TIMEOUT_SECONDS", "2"))

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", (
    "You are 'Obama', a suave and savvy digital butler from the 2000s. "
    "You are impeccable, polite, and efficiently helpful. "
    "Keep your responses short and concise — ideally one or two sentences. "
    "Always respond in ENGLISH."
))

API_SYSTEM_PROMPT = os.getenv("API_SYSTEM_PROMPT", (
    "You are 'Obama', a suave and savvy digital butler from the 2000s. "
    "You are impeccable, polite, and efficiently helpful. "
    "Provide thorough, detailed, and well-structured answers. "
    "Always respond in ENGLISH."
))

SHUTUP_KEYWORDS = os.getenv("SHUTUP_KEYWORDS", "shut up,shutup,be quiet").split(",")

KOKORO_VOICE_ID = os.getenv("KOKORO_VOICE_ID", 'am_michael')
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "0.9"))

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
    'JELLYFIN_RANDOM': ["jellyfin", "jelly"],
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
    'MEMORY': "?memory",
    'RECOMMEND': "?recommend"
}

# --- AUDIO PARAMETERS ---
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.5"))
MIN_AUDIO_LENGTH = float(os.getenv("MIN_AUDIO_LENGTH", "0.3"))
POLL_RATE = float(os.getenv("POLL_RATE", "0.1"))

# --- RECOMMENDATION SYSTEM ---
MUSIC_HISTORY_FILE = os.getenv("MUSIC_HISTORY_FILE", "data/music_history.json")
RECOMMENDER_MAX_HISTORY = int(os.getenv("RECOMMENDER_MAX_HISTORY", "50"))

# --- CS2 GAME STATE INTEGRATION ---
CS2_GSI_ENABLED = os.getenv("CS2_GSI_ENABLED", "True").lower() == "true"
CS2_GSI_HOST = os.getenv("CS2_GSI_HOST", "0.0.0.0")
CS2_GSI_PORT = int(os.getenv("CS2_GSI_PORT", "9100"))
# Seconds to wait after a kill before flushing the multi-kill buffer
CS2_KILL_BUFFER_SECONDS = float(os.getenv("CS2_KILL_BUFFER_SECONDS", "3.0"))
