# Mumble Butler 🎩

A voice-activated AI butler for Mumble. Listens for a wake word, transcribes speech, thinks with a local LLM, speaks back via TTS, and controls music — all on your own hardware.

## Features

| Category | Details |
|---|---|
| 🎙️ **Speech-to-Text** | [Moonshine](https://github.com/UsefulSensors/moonshine) streaming model via HuggingFace Transformers |
| 🔔 **Wake Word** | [openWakeWord](https://github.com/dscripka/openWakeWord) with real-time streaming detection + keyword fallback with fuzzy matching ([rapidfuzz](https://github.com/rapidfuzz/RapidFuzz)) |
| 🧠 **LLM API** | External [Ollama](https://ollama.com) API integration supporting any model with streaming responses |
| 🗣️ **Text-to-Speech** | [Chatterbox-Turbo](https://github.com/resemble-ai/chatterbox) voice cloning with sentence-level streaming for low latency |
| 🎵 **Music** | YouTube playback, LLM-seeded recommendations via iTunes API, history-aware deduplication — all via [botamusique](https://github.com/azlux/botamusique) |
| 💬 **Dual Interface** | Full command set via both voice and Mumble text chat |
| 🕒 **Hourly Reports** | Context-aware room status updates based on who's present and recent conversation |
| ⏰ **Reminders** | Natural language spoken reminders (`remind me in 10 minutes about standup`) |
| 🌐 **Web Search** | Live DuckDuckGo web search integration to answer questions with real-time up-to-date internet info |

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt   # also need: ffmpeg, a running Mumble server

# 2. Configure
cp .env.example .env              # edit with your server details + Ollama settings

# 3. Ensure Ollama is running and pull your preferred model
ollama run gemma4-e2b

# 4. Run
python main.py
```

## Architecture

```
main.py → MadnessBot (bot.py)
├── Brain         — LLM inference, memory, music recommendations
├── Ear           — Moonshine speech-to-text
├── Voice         — Chatterbox-Turbo text-to-speech
├── AudioManager  — Voice activity detection & per-user buffering
├── WakewordDetector — openWakeWord streaming detection
├── VoiceHandler  — Voice command routing (fuzzy keyword matching)
└── TextHandler   — Text chat command routing
```

**Async workers:** `tts_worker` (TTS queue → Mumble audio) · `audio_processing_worker` (voice clips → STT → command routing) · `hourly_report_worker` (periodic announcements)

## Commands

### Voice (say the wake word first)

| Command | Action |
|---|---|
| `<wake> <anything>` | Free-form LLM conversation |
| `<wake> play <query>` / `queue <query>` | YouTube playback |
| `<wake> music` | Random LLM-recommended song |
| `<wake> recommend <vibe>` | Curated recommendation |
| `<wake> stop` / `skip` / `repeat <n>` | Playback control |
| `<wake> volume <0-100>` / `mode <name>` | Volume & mode |
| `<wake> search <query>` | Live web search query |
| `<wake> remind me in <n> <unit> about <x>` | Spoken reminder |
| `<wake> forget` / `status` / `ping` | Memory, status, connectivity |
| `<wake> shut up` | Immediately stop speaking |

### Text Chat

| Command | Action |
|---|---|
| `?help` | List commands |
| `?status` | System health & uptime |
| `?search <query>` | Real-time web search summary |
| `?say <text>` | Speak arbitrary text |
| `?voice <name>` | Change TTS voice |
| `?prompt <text>` / `?prompt reset` | Dynamic system prompt |
| `?memory` / `?forget` / `?undo` | Memory controls |
| `?listen` | Toggle voice listening |
| `?play` `?stop` `?pause` `?resume` `?skip` `?clear` `?queue` `?now` | Music controls |
| `?volume <0-100>` / `?repeat <n>` / `?mode <name>` | Playback settings |
| `?recommend <vibe>` | LLM music recommendation |
| `?ping` | Pong! |

### TTS Voices

Custom voice reference WAV files stored in `data/voices/` (e.g. `michael.wav` *default*)

## Configuration

All settings via `.env` or environment variables. See [config.py](config.py) for defaults.

<details>
<summary><strong>Full variable reference</strong></summary>

| Variable | Default | Description |
|---|---|---|
| **Connection** | | |
| `MUMBLE_SERVER_IP` | `127.0.0.1` | Mumble server address |
| `MUMBLE_SERVER_PORT` | `64738` | Server port |
| `MUMBLE_BOT_USERNAME` | `Obama` | Bot display name |
| `MUMBLE_PASSWORD` | | Server password |
| `MUMBLE_TARGET_CHANNEL` | `General` | Channel to join |
| `MUMBLE_IGNORED_USERS` | `YoMusicBot` | Comma-separated ignore list |
| `MUMBLE_RECONNECT_DELAY` | `5` | Reconnect delay (seconds) |
| **LLM** | | |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint address |
| `OLLAMA_MODEL` | `gemma4-e2b` | Ollama model name |
| `LLM_DISABLE_THINKING` | `True` | Strip `<think>` tags |
| `LLM_MAX_TOKENS` | `1024` | Max tokens per response |
| `LLM_CONTEXT_SIZE` | `2000` | Context window size |
| **Speech Recognition** | | |
| `MOONSHINE_MODEL_SIZE` | `UsefulSensors/moonshine-streaming-medium` | Moonshine model |
| `MOONSHINE_DEVICE` | `cuda` | `cuda` or `cpu` |
| **Wake Word** | | |
| `WAKEWORD_LIBRARY` | `openwakeword` | Wake word engine |
| `WAKEWORD_MODEL_PATHS` | | Comma-separated custom model paths |
| `WAKEWORD_BUILTIN_MODELS` | `hey_jarvis` | Builtin openWakeWord models |
| `WAKEWORD_THRESHOLD` | `0.5` | Detection threshold |
| `ACTIVATION_KEYWORDS` | `obama,opama,opal,opa` | Keyword fallback list |
| **TTS** | | |
| `KOKORO_VOICE_ID` | `am_michael` | Default voice |
| `KOKORO_SPEED` | `0.9` | Speech speed |
| **Audio** | | |
| `SILENCE_THRESHOLD` | `0.5` | Silence gap to end clip (seconds) |
| `MIN_AUDIO_LENGTH` | `0.3` | Minimum clip length (seconds) |
| `POLL_RATE` | `0.1` | Audio poll interval (seconds) |
| `CHIME_FILE` | `chime.wav` | Activation chime sound |
| **Other** | | |
| `MEMORY_ENABLED` | `True` | Conversation memory |
| `SYSTEM_PROMPT` | *(see config.py)* | LLM system prompt |
| `MUSIC_HISTORY_FILE` | `data/music_history.json` | Recommendation history |
| `RECOMMENDER_MAX_HISTORY` | `50` | Max history entries |

</details>

## Music Integration

Requires [botamusique](https://github.com/azlux/botamusique) running in the same Mumble channel. The bot sends botamusique chat commands (`!yplay`, `!stop`, `!skip`, `!volume`, etc.) to control playback.

## Tests

```bash
python -m pytest tests/
```
