import ssl

# --- CONNECTION ---
SERVER_IP = "127.0.0.1"
SERVER_PORT = 64738
BOT_USERNAME = "Obama"
PASSWORD = "yo mumble server password"
TARGET_CHANNEL = "Michelle Obama's Lair"
IGNORED_USERS = ["YoMusicBot"]

# --- PATHS ---
STATS_FILE = "user_stats.csv"
CHIME_FILE = "chime.wav"
LLM_MODEL_PATH = "models/qwen2.5-3b-instruct-q4_k_m.gguf"

# --- AI CONFIG ---
WHISPER_MODEL_SIZE = "deepdml/faster-whisper-large-v3-turbo-ct2"
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE = "float16"

#Upto 32k and sum
LLM_CONTEXT_SIZE = 10000
LLM_GPU_LAYERS = -1
ACTIVATION_KEYWORD = "obama"

SYSTEM_PROMPT = (
    "You are 'Obama', a suave and savvy digital butler from the 2000s."
    "You are impeccable, polite, and efficiently helpful. "
    "Keep answers brief, polite, and helpful. Always respond in ENGLISH"
)

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
    'PLAY_FILE': ["file", "f"],         # New: Local file playback
    'REPEAT': ["repeat"]                # New: Repeat song
}

# --- OUTPUT COMMANDS ---
# The actual text commands sent to the Mumble server
MUMBLE_COMMANDS = {
    'VOLUME': "!volume",
    'PLAY_GENERIC': "!play",
    'PLAY_YOUTUBE': "!yplay",
    'PAUSE': "!pause",
    'SKIP': "!skip",
    'FILE': "!file",    # Maps to !file or !f
    'REPEAT': "!repeat"
}

# --- TEXT CHAT TRIGGERS ---
# Chat messages starting with these strings
TEXT_TRIGGERS = {
    'HELP': "?help",
    'LISTEN': "?listen",
    'FORGET': "?forget",
    'VOICE': "?voice",
    'SAY': "?say"
}

# --- AUDIO PARAMETERS ---
SILENCE_THRESHOLD = 0.5
MIN_AUDIO_LENGTH = 0.3
POLL_RATE = 0.1

# --- SSL FIX (Python 3.12+) ---
#Lmao, fix it fo reeal
def patch_ssl():
    if not hasattr(ssl, 'wrap_socket'):
        def wrap_socket(sock, **kwargs):
            context = ssl.SSLContext(kwargs.get('ssl_version', ssl.PROTOCOL_TLS_CLIENT))
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context.wrap_socket(sock, server_hostname=kwargs.get('server_hostname'))
        ssl.wrap_socket = wrap_socket
