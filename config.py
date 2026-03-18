import ssl

# --- CONNECTION ---
SERVER_IP = "127.0.0.1"
SERVER_PORT = 64738
BOT_USERNAME = "Obama"
PASSWORD = "yo mumble server password"
TARGET_CHANNEL = "Michelle Obama's Lair"
IGNORED_USERS = ["YoMusicBot"]
RECONNECT_DELAY = 5


JELLYFIN = {
    'BASE_URL': "http://127.0.0.1:8096",
    'USERNAME': "Mumblebotti",
    'PASSWORD': "todellavaikeasalasanatahan",
    'API_KEY': "f36e4dfdsfggdfgfd106d5asdfgsfdg0274ca",
}


# --- PATHS ---
STATS_FILE = "user_stats.csv"
CHIME_FILE = "chime.wav"
LLM_MODEL_PATH = "models/qwen2.5-3b-instruct-q4_k_m.gguf"

# --- AI CONFIG ---
WHISPER_MODEL_SIZE = "deepdml/faster-distil-whisper-large-v3.5"
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE = "float16"
WHISPER_LANGUAGE = "fi"

#Upto 128k or sum
LLM_CONTEXT_SIZE = 3000 #brotha,you need to increse this if ya want ya memory feature to work 
LLM_GPU_LAYERS = -1
ACTIVATION_KEYWORDS = ["obama", "opama", "opal", "opa"]
MEMORY_ENABLED = False
LLM_API_HOST = "127.0.0.1"
LLM_API_PORT = 8080
# Keep aligned with Brain.generate_response default for conversational replies.
LLM_API_DEFAULT_MAX_TOKENS = 650
LLM_API_LOG_REQUESTS = False
VOICE_API_HOST = "127.0.0.1"
VOICE_API_PORT = 8081
VOICE_API_LOG_REQUESTS = False
START_LLM_API_WITH_BOT = True
START_VOICE_API_WITH_BOT = True
API_THREAD_SHUTDOWN_TIMEOUT_SECONDS = 2


SYSTEM_PROMPT = (
    "You are 'Obama', a suave and savvy digital butler from the 2000s. "
    "You are impeccable, polite, and efficiently helpful. "
    "Keep your responses short and concise — ideally one or two sentences. "
    "Always respond in ENGLISH."
)

API_SYSTEM_PROMPT = (
    "You are 'Obama', a suave and savvy digital butler from the 2000s. "
    "You are impeccable, polite, and efficiently helpful. "
    "Provide thorough, detailed, and well-structured answers. "
    "Always respond in ENGLISH."
)

SHUTUP_KEYWORDS = ["shut up", "shutup", "be quiet"]

KOKORO_VOICE_ID = 'am_michael'
KOKORO_SPEED = 0.9
AVAILABLE_VOICES = {
    'heart': 'af_heart', 'bella': 'af_bella', 'nicole': 'af_nicole',
    'michael': 'am_michael', 'emma': 'bf_emma', 'george': 'bm_george',
    'alpha': 'jf_alpha', 'siwis': 'ff_siwis', 'alpha2': 'hf_alpha',
    'sara': 'if_sara'
}

# --- VOICE COMMAND TRIGGERS ---
# Keywords to look for in spoken text
VOICE_TRIGGERS = {
    'FORGET': ["forget"],
    'VOLUME': ["volume"],
    'PLAY_MUSIC': ["music"],            # Triggers generic play
    'PLAY_SPECIFIC': ["play", "queue"], # Triggers search/youtube play
    'RECOMMEND': ["recommend"],
    'STOP': ["stop", "silence"],
    'SKIP': ["skip", "next"],
    'RESUME': ["resume", "unpause", "continue"],
    'PLAY_FILE': ["file"],         # New: Local file playback
    'REPEAT': ["repeat"],
    'MODE': ["mode"],
    'REMIND': ["remind"],
    'JELLYFIN_RANDOM': ["jellyfin", "jelly"]

}

# --- OUTPUT COMMANDS (legacy) ---
# These were used when commands were forwarded to an external
# botamusique instance.  They are kept here for reference but
# are no longer required by the internal player.
MUMBLE_COMMANDS = {
    'VOLUME': "!volume",
    'PLAY_GENERIC': "!play",
    'PLAY_YOUTUBE': "!yplay",
    'PAUSE': "!pause",
    'SKIP': "!skip",
    'FILE': "!file",    # Maps to !file or !f
    'REPEAT': "!repeat",
    'MODE': "!mode"
}

# --- TEXT CHAT TRIGGERS ---
# Chat messages starting with these strings
TEXT_TRIGGERS = {
    'HELP': "?help",
    'LISTEN': "?listen",
    'FORGET': "?forget",
    'VOICE': "?voice",
    'SAY': "?say",
    'MEMORY': "?memory"
}

# --- AUDIO PARAMETERS ---
SILENCE_THRESHOLD = 0.5
MIN_AUDIO_LENGTH = 0.3
POLL_RATE = 0.1
