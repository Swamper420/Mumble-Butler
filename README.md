# Mumble Butler 🎩

A voice-activated AI butler for Mumble servers. Listens to your voice, understands natural language via a local LLM, speaks back with a TTS voice, and controls music playback — all running entirely on your own hardware.

---

## Features

- 🎙️ **Voice recognition** — Transcribes speech with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- 🧠 **Local LLM** — Conversational responses via [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) (GGUF models)
- 🔊 **Text-to-speech** — Speaks responses using [Kokoro](https://github.com/hexgrad/kokoro)
- 🎵 **Music control** — Forwards commands to [botamusique](https://github.com/azlux/botamusique) via Mumble chat
- 🎯 **Smart recommendations** — LLM-seeded music discovery via iTunes Search API
- 🕒 **Hourly reports** — Periodic room status updates based on who's around and recent chat
- 💬 **Text chat commands** — Full command set available via Mumble text chat
- 🔔 **Voice reminders** — Schedule spoken reminders with natural language

---

## Requirements

- Python 3.10+
- `ffmpeg` (for audio processing)
- A running Mumble server
- A GGUF-format language model (e.g. `gemma-3-8b-it-q4_k_m.gguf`)
- Optionally: a CUDA-capable GPU for faster inference and transcription

```
pymumble_py3
faster-whisper
llama-cpp-python
kokoro
numpy
python-dotenv
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Setup

### 1. Copy the example environment file

```bash
cp .env.example .env
```

### 2. Configure `.env`

```env
# Mumble connection
MUMBLE_SERVER_IP=your.mumble.server
MUMBLE_SERVER_PORT=64738
MUMBLE_BOT_USERNAME=Obama
MUMBLE_PASSWORD=your_mumble_password
MUMBLE_TARGET_CHANNEL=General
MUMBLE_IGNORED_USERS=YoMusicBot

# LLM model
LLM_MODEL_PATH=models/gemma-3-8b-it-q4_k_m.gguf
LLM_PROMPT_FORMAT=gemma        # "gemma" or "chatml"
LLM_DISABLE_THINKING=True      # strip <think> tags (for reasoning models)

# Speech recognition
WHISPER_DEVICE=cuda            # or "cpu"
WHISPER_COMPUTE=float16        # or "int8" for CPU
WHISPER_LANGUAGE=fi            # language code (e.g. "en", "fi")

# LLM inference
LLM_CONTEXT_SIZE=2000
LLM_GPU_LAYERS=-1              # -1 = all layers on GPU

# Memory
MEMORY_ENABLED=True
```

### 3. Place your model

Put your GGUF model in the `models/` directory, then set `LLM_MODEL_PATH` accordingly.

### 4. Run

```bash
python main.py
```

---

## Architecture

```
main.py
└── MadnessBot (bot.py)
    ├── Brain (modules/brain.py)       — LLM inference, memory, music recommendations
    ├── Ear (modules/ears.py)          — Whisper speech-to-text
    ├── Voice (modules/voice.py)       — Kokoro text-to-speech
    ├── AudioManager (modules/audio_manager.py) — Voice activity detection & buffering
    ├── VoiceHandler (handlers/voice.py)  — Voice command routing
    └── TextHandler (handlers/text.py)   — Text chat command routing
```

The bot runs three concurrent async workers:
- **`tts_worker`** — Consumes the TTS queue and streams audio to Mumble
- **`audio_processing_worker`** — Polls completed voice clips and routes them through Whisper + VoiceHandler
- **`hourly_report_worker`** — Generates and announces periodic room status updates

---

## Voice Commands

All voice commands require an **activation keyword** first (default: `obama`, `opama`, `opal`, `opa`).

| Say | Action |
|---|---|
| `[keyword] forget` | Wipe conversation memory |
| `[keyword] volume 70` | Set music volume (0–100) |
| `[keyword] play <query>` | Play a YouTube search via botamusique |
| `[keyword] queue <query>` | Add to queue |
| `[keyword] music` | Play a random LLM-recommended song |
| `[keyword] recommend <vibe>` | Get an LLM-curated song recommendation |
| `[keyword] stop` / `silence` | Stop music playback |
| `[keyword] skip` / `next` | Skip current track |
| `[keyword] repeat 3` | Repeat current track N times |
| `[keyword] mode <name>` | Set mode: `one-shot`, `autoplay`, `repeat`, `random` |
| `[keyword] file <path>` | Play a local file via botamusique |
| `[keyword] remind me in 10 minutes about standup` | Schedule a spoken reminder |
| `[keyword] status` | Hear a status report |
| `[keyword] ping` | Connectivity check |
| `[keyword] shut up` | Immediately stop the bot from speaking |
| `[keyword] <anything else>` | Free-form LLM conversation |

---

## Text Chat Commands

Send these directly in Mumble chat.

| Command | Action |
|---|---|
| `?help` | List all available commands |
| `?status` | Show system health (LLM, STT, TTS, uptime, memory) |
| `?listen` | Toggle voice listening on/off |
| `?forget` | Wipe conversation memory |
| `?memory` | Toggle conversation memory on/off |
| `?undo` | Remove the last interaction from memory |
| `?prompt <text>` | Set a live custom system prompt |
| `?prompt reset` | Restore the default system prompt |
| `?voice <name>` | Change TTS voice (see voices below) |
| `?say <text>` | Make the bot speak arbitrary text |
| `?recommend <vibe>` | Queue an LLM-recommended song |
| `?play <query>` | Play a YouTube search |
| `?now` | Request now-playing info |
| `?queue` | Show the music queue |
| `?skip` | Skip current track |
| `?clear` | Clear the music queue |
| `?stop` | Stop music |
| `?pause` | Pause music |
| `?resume` | Resume music |
| `?volume <0-100>` | Set volume |
| `?repeat <n>` | Repeat current track N times |
| `?mode <name>` | Set playback mode |
| `?ping` | Pong! |

---

## Available TTS Voices

Set with `?voice <name>` or via `KOKORO_VOICE_ID` in `.env`.

| Name | Voice ID |
|---|---|
| `michael` | `am_michael` *(default)* |
| `heart` | `af_heart` |
| `bella` | `af_bella` |
| `nicole` | `af_nicole` |
| `emma` | `bf_emma` |
| `george` | `bm_george` |
| `alpha` | `jf_alpha` |
| `siwis` | `ff_siwis` |
| `sara` | `if_sara` |

---

## Configuration Reference

All settings can be set in `.env` or as environment variables. Config is loaded in [`config.py`](config.py).

| Variable | Default | Description |
|---|---|---|
| `MUMBLE_SERVER_IP` | `127.0.0.1` | Mumble server address |
| `MUMBLE_SERVER_PORT` | `64738` | Mumble server port |
| `MUMBLE_BOT_USERNAME` | `Obama` | Bot's display name |
| `MUMBLE_PASSWORD` | *(empty)* | Server password |
| `MUMBLE_TARGET_CHANNEL` | `General` | Channel to join on connect |
| `MUMBLE_IGNORED_USERS` | `YoMusicBot` | Comma-separated users to ignore |
| `MUMBLE_RECONNECT_DELAY` | `5` | Seconds before reconnect attempt |
| `LLM_MODEL_PATH` | `models/gemma-3-8b-it-q4_k_m.gguf` | Path to GGUF model |
| `LLM_PROMPT_FORMAT` | `gemma` | Prompt format: `gemma` or `chatml` |
| `LLM_DISABLE_THINKING` | `True` | Strip `<think>` tags from output |
| `LLM_MAX_TOKENS` | `1024` | Max tokens per voice response |
| `LLM_CONTEXT_SIZE` | `2000` | LLM context window size |
| `LLM_GPU_LAYERS` | `-1` | GPU layers (`-1` = all) |
| `WHISPER_MODEL_SIZE` | `deepdml/faster-distil-whisper-large-v3.5` | Whisper model |
| `WHISPER_DEVICE` | `cuda` | `cuda` or `cpu` |
| `WHISPER_COMPUTE` | `float16` | Compute type (`float16`, `int8`) |
| `WHISPER_LANGUAGE` | `fi` | Language code for transcription |
| `ACTIVATION_KEYWORDS` | `obama,opama,opal,opa` | Comma-separated wake words |
| `SYSTEM_PROMPT` | *(see config.py)* | LLM system prompt |
| `MEMORY_ENABLED` | `True` | Enable conversation memory |
| `KOKORO_VOICE_ID` | `am_michael` | Default TTS voice ID |
| `KOKORO_SPEED` | `0.9` | TTS speech speed |
| `SILENCE_THRESHOLD` | `0.5` | Seconds of silence to end a voice clip |
| `MIN_AUDIO_LENGTH` | `0.3` | Minimum clip length to process (seconds) |
| `POLL_RATE` | `0.1` | Audio polling interval (seconds) |
| `CHIME_FILE` | `chime.wav` | Audio file to play on activation |
| `MUSIC_HISTORY_FILE` | `data/music_history.json` | Music recommendation history |
| `RECOMMENDER_MAX_HISTORY` | `50` | Max entries to keep in music history |

---

## Music Integration

The bot integrates with [botamusique](https://github.com/azlux/botamusique) by sending chat commands to the Mumble channel. Ensure botamusique is running in the same channel for music commands to work.

Botamusique commands used:

| Action | Command sent |
|---|---|
| Play YouTube | `!yplay <query>` |
| Play (generic) | `!play` |
| Pause | `!pause` |
| Stop | `!stop` |
| Skip | `!skip` |
| Volume | `!volume <level>` |
| Repeat | `!repeat <n>` |
| Mode | `!mode <name>` |
| Now playing | `!np` |
| Queue | `!queue` |
| Clear | `!clear` |
| Play file | `!file <path>` |

---

## Running Tests

```bash
python -m pytest tests/
```
