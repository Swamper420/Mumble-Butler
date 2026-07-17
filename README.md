# 🎙️ Mumble-Butler

A self-hosted AI voice butler for [Mumble](https://www.mumble.info/) — listens to voice in your channel, answers questions, and controls music.

Built around a local LLM ([llama-cpp-python](https://github.com/abetlen/llama-cpp-python)), [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for speech-to-text, and [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) for text-to-speech — everything runs on-device, no cloud required.

---

## Features

### 🧠 AI Conversation
- Wake-word activation (default: `obama`, `opama`, `opal`, `opa`)
- Answers natural language questions via a local LLM
- Per-user conversation memory (toggleable)

### 🎵 Music Control
Forwards commands to [botamusique](https://github.com/azlux/botamusique) via Mumble text chat:

| Voice command | Action |
|---|---|
| *Obama, play \<query\>* | Queue a YouTube track |
| *Obama, music* | Queue a random AI-recommended track |
| *Obama, recommend \<vibe\>* | AI song recommendation based on mood/chat context |
| *Obama, skip* / *next* | Skip current track |
| *Obama, stop* / *silence* | Stop playback |
| *Obama, volume \<0–100\>* | Set volume |
| *Obama, repeat \<n\>* | Repeat current track n times |
| *Obama, mode \<one-shot\|autoplay\|repeat\|random\>* | Set playback mode |

### ⏰ Other Features
- **Reminders** — *"Obama, remind me in 10 minutes to check the oven"*
- **Hourly status report** — LLM-generated hourly room update mentioning active users and conversation vibe
- **Status check** — *"Obama, status"* → uptime, LLM/STT/TTS health
- **Ping** — *"Obama, ping"* → "Pong! I am here."
- **Forget** — *"Obama, forget"* → wipes conversation memory

### 🌐 HTTP APIs (local network)
Two optional HTTP servers start alongside the bot:

| Server | Default port | Endpoints |
|---|---|---|
| LLM API | `8080` | `POST /query`, `GET /health`, `POST /reset_memory` |
| Voice API (STT) | `8081` | `POST /transcribe`, `GET /health` |

---

## Architecture

```
main.py
└── bot.py  (MadnessBot)
    ├── modules/
    │   ├── brain.py        — LLM wrapper, memory, song recommender
    │   ├── ears.py         — faster-whisper STT
    │   ├── voice.py        — Kokoro TTS → 48 kHz PCM
    │   ├── audio_manager.py — per-user audio stream buffering
    │   ├── recommender.py  — iTunes-backed music recommendation
    │   ├── llm_api.py      — local HTTP LLM API server
    │   └── voice_api.py    — local HTTP STT API server
    └── handlers/
        ├── voice.py        — wake-word detection + voice command routing
        └── text.py         — Mumble text chat command routing
```

---

## Requirements

- Python 3.11+
- `ffmpeg` (for chime loading)
- CUDA GPU recommended for real-time STT + LLM inference
- A running Mumble server
- [botamusique](https://github.com/azlux/botamusique) for music playback (optional)

### Python dependencies

```
pip install pymumble_py3 faster-whisper llama-cpp-python kokoro numpy python-dotenv
```

Or:

```bash
pip install -r requirements.txt
```

---

## Setup

1. Clone this repository.
2. Install dependencies (see above).
3. Download a GGUF format LLM model (e.g. `gemma-3-8b-it-q4_k_m.gguf` or similar) and place it under `models/`.
4. Copy `.env.example` to `.env` and fill in your Mumble server address.
5. Run the bot:

```bash
python main.py
```

### Forcing HTTP APIs on
By default, the HTTP servers only launch if `START_LLM_API_WITH_BOT` and `START_VOICE_API_WITH_BOT` are set to `True` in `.env`.
To override this and force both APIs to run alongside the bot:
```bash
python main.py --api
```

### Running only the HTTP APIs (No Mumble Connection)
To run only the LLM & Voice transcribing servers as a lightweight microservice (without connecting the bot to any Mumble server):
```bash
python main.py --api-only
```

---

## Environment Variables (`.env`)

Configure the bot by setting these variables in your `.env` file:

### Connection

| Variable | Default | Description |
|---|---|---|
| `MUMBLE_SERVER_IP` | `127.0.0.1` | Mumble server address |
| `MUMBLE_SERVER_PORT` | `64738` | Mumble server port |
| `MUMBLE_BOT_USERNAME` | `Obama` | Bot username |
| `MUMBLE_PASSWORD` | *(empty)* | Server password (if required) |
| `MUMBLE_TARGET_CHANNEL` | `General` | Channel to join |
| `MUMBLE_IGNORED_USERS` | `YoMusicBot` | Users to ignore (comma-separated) |
| `MUMBLE_RECONNECT_DELAY` | `5` | Reconnection interval (seconds) |

### LLM / Brain

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL_PATH` | `models/gemma-3-8b-it-q4_k_m.gguf` | Path to GGUF model |
| `LLM_PROMPT_FORMAT` | `gemma` | Prompt format (`gemma` or `chatml`) |
| `LLM_CONTEXT_SIZE` | `2000` | Context window size |
| `LLM_GPU_LAYERS` | `-1` | Number of layers to offload to GPU (`-1` = all) |
| `LLM_DISABLE_THINKING` | `True` | Forces the model to respond concisely without thoughts |
| `LLM_MAX_TOKENS` | `1024` | Max tokens for conversation response |

### STT / ears

| Variable | Default | Description |
|---|---|---|
| `WHISPER_MODEL_SIZE` | `deepdml/faster-distil-whisper-large-v3.5` | Whisper model ID |
| `WHISPER_DEVICE` | `cuda` | Run Whisper on `cuda` or `cpu` |
| `WHISPER_COMPUTE` | `float16` | Precision (`float16` or `int8`) |
| `WHISPER_LANGUAGE` | `fi` | Target language |
| `SILENCE_THRESHOLD` | `0.5` | Silence threshold |
| `MIN_AUDIO_LENGTH` | `0.3` | Minimum audio length in seconds |
| `POLL_RATE` | `0.1` | User audio check interval (seconds) |

### TTS / voice

| Variable | Default | Description |
|---|---|---|
| `KOKORO_VOICE_ID` | `am_michael` | Default Kokoro voice ID |
| `KOKORO_SPEED` | `0.9` | Speech speed |

### Behavior

| Variable | Default | Description |
|---|---|---|
| `ACTIVATION_KEYWORDS` | `obama,opama,opal,opa` | Wake words (comma-separated) |
| `MEMORY_ENABLED` | `True` | Enable per-user conversation memory |
| `SHUTUP_KEYWORDS` | `shut up,shutup,be quiet` | Instantly interrupt TTS |
| `SYSTEM_PROMPT` | *(butler persona)* | LLM system prompt |

### HTTP APIs

| Variable | Default | Description |
|---|---|---|
| `START_LLM_API_WITH_BOT` | `True` | Start LLM HTTP API on launch |
| `LLM_API_HOST` | `127.0.0.1` | LLM API bind host |
| `LLM_API_PORT` | `8080` | LLM API port |
| `LLM_API_DEFAULT_MAX_TOKENS` | `150` | Default response length |
| `LLM_API_MEMORY_ENABLED` | `True` | API session memory |
| `START_VOICE_API_WITH_BOT` | `True` | Start STT HTTP API on launch |
| `VOICE_API_HOST` | `127.0.0.1` | Voice API bind host |
| `VOICE_API_PORT` | `8081` | Voice API port |

---

## Text Chat Commands

Type these directly in the Mumble channel:

| Command | Description |
|---|---|
| `?help` | List all commands |
| `?status` | System health (LLM, STT, TTS, uptime) |
| `?listen` | Toggle voice listening on/off |
| `?forget` | Wipe conversation memory |
| `?memory` | Toggle memory on/off |
| `?voice <name>` | Change TTS voice (`heart`, `bella`, `nicole`, `michael`, `emma`, `george`, `alpha`, `siwis`, `sara`) |
| `?say <text>` | Make the bot speak arbitrary text |
| `?recommend <vibe>` | AI music recommendation |
| `?prompt <text>` | Set a custom system prompt on the fly |
| `?prompt reset` | Restore default system prompt |
| `?undo` | Forget the last exchange from memory |
| `?play <query>` | Queue a YouTube track |
| `?now` | Show now playing |
| `?queue` | Show playback queue |
| `?skip` | Skip current track |
| `?stop` | Stop playback |
| `?pause` / `?resume` | Pause / resume |
| `?volume <0–100>` | Set volume |
| `?repeat <n>` | Repeat n times |
| `?mode <mode>` | Set playback mode |
| `?clear` | Clear the queue |
| `?ping` | Pong! |

---

## Available TTS Voices

| Key | Voice ID | Character |
|---|---|---|
| `heart` | `af_heart` | Warm, feminine |
| `bella` | `af_bella` | Diva |
| `nicole` | `af_nicole` | Neutral feminine |
| `michael` | `am_michael` | Default male |
| `emma` | `bf_emma` | British feminine |
| `george` | `bm_george` | British male |
| `alpha` | `jf_alpha` | Japanese feminine |
| `siwis` | `ff_siwis` | French feminine |
| `sara` | `if_sara` | Italian feminine |

---

## HTTP API Reference

### LLM API (`http://localhost:8080`)

**Query the LLM:**
```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of Finland?", "max_tokens": 200}'
```

**Health check:**
```bash
curl http://localhost:8080/health
```

**Reset API session memory:**
```bash
curl -X POST http://localhost:8080/reset_memory
```

### Voice API (`http://localhost:8081`)

**Transcribe raw 16-bit PCM audio (base64 encoded):**
```bash
curl -X POST http://localhost:8081/transcribe \
  -H "Content-Type: application/json" \
  -d '{"pcm_base64": "<base64_encoded_pcm>"}'
```

**Health check:**
```bash
curl http://localhost:8081/health
```

---

## License

MIT
