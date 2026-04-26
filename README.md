# 🎙️ Mumble-Butler

A self-hosted AI voice butler for [Mumble](https://www.mumble.info/) — listens to voice in your channel, answers questions, controls music, and now provides live CS2 match commentary.

Built around a local LLM ([llama-cpp-python](https://github.com/abetlen/llama-cpp-python)), [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for speech-to-text, and [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) for text-to-speech — everything runs on-device, no cloud required.

---

## Features

### 🧠 AI Conversation
- Wake-word activation (default: `obama`, `opama`, `opal`, `opa`)
- Answers natural language questions via a local LLM
- Per-user conversation memory (toggleable)
- Per-user random personality assignment on channel join — five distinct personas, each with their own TTS voice

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

### 🎮 CS2 Live Commentary
Receives real-time match data from CS2 via **Game State Integration** (GSI) and announces events in the Mumble channel:

- **Kill feed** — buffers kills for 3 seconds, then delivers in-character LLM commentary scaled to the event (single kill → mild, double → excited, ACE → unhinged)
- **Round-end debrief** — post-round economic analysis: who can full-buy, who is forced to eco, K/D/A highlights, and score update
- **Bomb planted** — instant quip when the bomb goes down
- **Game phase announcements** — half-time, game over, warmup

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
    │   ├── brain.py        — LLM wrapper, memory, song recommender, CS2 commentary
    │   ├── ears.py         — faster-whisper STT
    │   ├── voice.py        — Kokoro TTS → 48 kHz PCM
    │   ├── audio_manager.py — per-user audio stream buffering
    │   ├── cs2_gsi.py      — CS2 Game State Integration HTTP receiver + event engine
    │   ├── recommender.py  — iTunes-backed music recommendation
    │   ├── llm_api.py      — local HTTP LLM API server
    │   └── voice_api.py    — local HTTP STT API server
    ├── handlers/
    │   ├── voice.py        — wake-word detection + voice command routing
    │   └── text.py         — Mumble text chat command routing
    └── personalities.py    — per-user persona definitions
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

### 1. Clone and configure

```bash
git clone https://github.com/Swamper420/Mumble-Butler.git
cd Mumble-Butler
cp .env.example .env
```

Edit `.env` with your values (see [Configuration](#configuration)).

### 2. Download a GGUF model

Place a `llama-cpp`-compatible GGUF model in the `models/` directory.  
Default expected path: `models/qwen2.5-3b-instruct-q4_k_m.gguf`

Recommended: [Qwen2.5-3B-Instruct-Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF)

### 3. Run

```bash
python main.py
```

---

## Configuration

All settings can be overridden via `.env` or environment variables.

### Mumble connection

| Variable | Default | Description |
|---|---|---|
| `MUMBLE_SERVER_IP` | `127.0.0.1` | Mumble server IP |
| `MUMBLE_SERVER_PORT` | `64738` | Mumble server port |
| `MUMBLE_BOT_USERNAME` | `Obama` | Bot display name |
| `MUMBLE_PASSWORD` | *(empty)* | Server password |
| `MUMBLE_TARGET_CHANNEL` | `General` | Channel to join on connect |
| `MUMBLE_IGNORED_USERS` | `YoMusicBot` | Comma-separated users to ignore |
| `MUMBLE_RECONNECT_DELAY` | `5` | Seconds between reconnect attempts |

### AI models

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL_PATH` | `models/qwen2.5-3b-instruct-q4_k_m.gguf` | Path to GGUF model |
| `LLM_CONTEXT_SIZE` | `2000` | LLM context window tokens |
| `LLM_GPU_LAYERS` | `-1` | GPU layers (`-1` = all) |
| `WHISPER_MODEL_SIZE` | `deepdml/faster-distil-whisper-large-v3.5` | Whisper model |
| `WHISPER_DEVICE` | `cuda` | `cuda` or `cpu` |
| `WHISPER_COMPUTE` | `float16` | Whisper compute type |
| `WHISPER_LANGUAGE` | `fi` | STT language code |
| `KOKORO_VOICE_ID` | `am_michael` | Default TTS voice |
| `KOKORO_SPEED` | `0.9` | TTS speech speed |

### Behaviour

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

### CS2 Game State Integration

| Variable | Default | Description |
|---|---|---|
| `CS2_GSI_ENABLED` | `True` | Enable CS2 GSI listener |
| `CS2_GSI_HOST` | `0.0.0.0` | Bind host (use `0.0.0.0` for LAN) |
| `CS2_GSI_PORT` | `9100` | Port CS2 will POST to |
| `CS2_KILL_BUFFER_SECONDS` | `3.0` | Multi-kill aggregation window |

### Jellyfin (optional)

| Variable | Default | Description |
|---|---|---|
| `JELLYFIN_BASE_URL` | `http://127.0.0.1:8096` | Jellyfin server URL |
| `JELLYFIN_USERNAME` | *(empty)* | Jellyfin username |
| `JELLYFIN_PASSWORD` | *(empty)* | Jellyfin password |
| `JELLYFIN_API_KEY` | *(empty)* | Jellyfin API key |

---

## CS2 Game State Integration Setup

CS2 pushes live match data to a URL you configure. The bot receives it and delivers in-character commentary.

### 1. Copy the config file

Copy `gamestate_integration_mumblebutler.cfg` from the repo root to:

```
C:\...\Counter-Strike Global Offensive\game\csgo\cfg\
```

### 2. Edit the IP

Open the file and replace `192.168.X.X` with the **LAN IP of the machine running Mumble-Butler**:

```
"uri" "http://192.168.X.X:9100/"
```

### 3. Launch CS2

CS2 auto-loads all `gamestate_integration_*.cfg` files on startup. No launch options needed.

> **Note:** `allplayers_*` stats (all players' health, money, weapons) are only available when **spectating or watching GOTV**. In a live match CS2 provides only your own player state (anti-cheat restriction).

### What the bot announces

| Event | Announcement |
|---|---|
| Kill(s) detected | LLM commentary scaled to kill count — single, double, triple, quad, ACE |
| Round over | Economic debrief: winner, score, per-player eco status and K/D/A |
| Bomb planted | *"Bomb planted. Tick tock."* |
| Half-time | *"Half time. Switch sides."* |
| Game over | *"Game over. Good game everyone."* |

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

## Personalities

On joining the bot's channel, each user is randomly assigned one of five personas. The bot uses that persona's voice and system prompt for all responses to that user.

| Persona | Voice | Character |
|---|---|---|
| The Toxic Diva | Bella | Vain, judgmental, considers herself superior |
| The Depressed Android | Michael | Marvin-like, finds everything pointless |
| The Drill Sergeant | George | Aggressive, calls you maggot, demands results |
| The Space Cadet | Emma | Cosmic vibes, easily distracted, very chill |
| The Victorian Gossip | Heart | Dramatic whispers, obsessed with scandal |

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
