# Mumble Butler 🎩

A voice-activated AI butler for Mumble. Listens for a wake word, transcribes speech, processes requests with a local LLM, speaks back via TTS, and controls music — all on your own hardware.

## Features

| Category | Details |
|---|---|
| 🎙️ **Speech-to-Text** | External REST STT API (`POST /api/v1/transcribe`) serving Whisper / CTranslate2 models (e.g. `RASMUS/whisper-large-v3-turbo-finnish-ct2`) |
| 🔔 **Wake Word** | [openWakeWord](https://github.com/dscripka/openWakeWord) with real-time streaming detection |
| 🧠 **LLM API** | External [Ollama](https://ollama.com) API integration supporting any model with streaming responses |
| 🗣️ **Text-to-Speech** | OpenAI-compatible TTS API with custom voice selection and sentence-level streaming |
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
main.py → MadnessBot (bot.py) → self.backend: VoiceBackend
├── MumbleBackend (backends/mumble_backend.py) — pymumble voice + text (default)
└── TeamspeakBackend (backends/teamspeak_backend.py) — USE_TEAMSPEAK=true
    ├── QueryClient (SSH :10022) — text / presence / move
    └── BridgeSupervisor → bridge/ts-voice-bridge/ (Node + @honeybbq/teamspeak-client)
        RX: TS Opus → 48k PCM → UDP :5001 → AudioManager.add_audio()
        TX: TTS 48k PCM → UDP :5002 → Opus → sendVoice()
├── Brain         — LLM inference, memory, music recommendations
├── Ear           — External STT REST API client
├── Voice         — External OpenAI-compatible TTS API
├── AudioManager  — Voice activity detection & per-user buffering
├── WakewordDetector — openWakeWord streaming detection
├── VoiceHandler  — Voice command routing
└── TextHandler   — Text chat command routing (handle_text core, both backends)
```

PCM contract (both backends): 48 kHz mono s16le. `AudioManager`,
`UserVoiceStream`, `Ear.transcribe` and `Voice.generate_pcm` are unchanged.

**Async workers:** `tts_worker` (TTS queue → backend audio) · `audio_processing_worker` (voice clips → STT → command routing) · `hourly_report_worker` (periodic announcements)

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
| `?recommend <vibe>` | LLM music recommendation (verified, no repeats) |
| `?another` / `?dislike` / `?history` | Fresh pick / skip+replace / recent picks |
| `?ping` | Pong! |

### TTS Voices

Dynamic voice IDs fetched via external TTS REST API (`GET /api/v1/voices`). Switch active voice using `?voice <name>`.

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
| `LLM_MAX_TOKENS` | `1024` | Max tokens per response |
| `LLM_CONTEXT_SIZE` | `2000` | Context window size |
| **Speech Recognition** | | |
| `STT_API_URL` | `http://localhost:8001` | STT REST API endpoint URL (`POST /api/v1/transcribe`) |
| `STT_BEAM_SIZE` | `5` | Beam size for search decoding |
| `STT_VAD_FILTER` | `True` | Enable VAD silence filtering |
| `STT_WORD_TIMESTAMPS` | `False` | Include word-level timestamps |
| `STT_INITIAL_PROMPT` | | Context or style prompt for transcription |
| `STT_TIMEOUT` | `15` | Request timeout in seconds |
| **Wake Word** | | |
| `WAKEWORD_LIBRARY` | `openwakeword` | Wake word engine |
| `WAKEWORD_MODEL_PATHS` | | Comma-separated custom model paths |
| `WAKEWORD_BUILTIN_MODELS` | `hey_jarvis` | Builtin openWakeWord models |
| `WAKEWORD_THRESHOLD` | `0.5` | Detection threshold |
| `ACTIVATION_KEYWORDS` | `obama,opama,opal,opa` | Keyword fallback list |
| **TTS & Voice API** | | |
| `TTS_API_URL` | `http://localhost:8000` | Base URL for external TTS server (`POST /api/v1/tts`) |
| `TTS_VOICE` | `mieto_fi` | Default voice identifier |
| `TTS_LANGUAGE` | `fi` | Target TTS synthesis language |
| `TTS_SPEED` | `1.0` | Speech playback rate multiplier |
| `TTS_NUM_STEP` | `32` | Diffusion synthesis step count |
| `TTS_GUIDANCE_SCALE` | `2.0` | Guidance scale multiplier |
| `TTS_RESPONSE_FORMAT` | `wav` | Returned audio format |
| `TTS_SEED` | `42` | Random seed for synthesis reproducible output |
| `TTS_TIMEOUT` | `30` | Request timeout in seconds |
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

> 🎵 Music is Mumble-only. On TeamSpeak (`USE_TEAMSPEAK=true`) every music
> command replies `🎵 Music via botamusique is not supported on TeamSpeak yet.`
> and nothing is sent to TS chat.

## TeamSpeak 6 support (`USE_TEAMSPEAK=true`)

Mumble remains the default. Set `USE_TEAMSPEAK=true` to join a TeamSpeak 6
server with full voice via the bridge sidecar (not text-only).

```bash
cp .env.example .env   # fill TS6_* below
USE_TEAMSPEAK=True python main.py
```

| Variable | Default | Description |
|---|---|---|
| `USE_TEAMSPEAK` | `False` | `true` = TeamSpeak 6 backend, `false` = Mumble |
| `TS6_HOST` | `127.0.0.1` | TS6 server address (query + voice) |
| `TS6_QUERY_PORT` | `10022` | SSH ServerQuery port (`:10022/tcp`) |
| `TS6_QUERY_USER` / `TS6_QUERY_PASSWORD` | `serveradmin` / empty | Query login (see server `TSSERVER_QUERY_ADMIN_PASSWORD`) |
| `TS6_SERVER_ID` | `1` | Virtual server id (`use <id>`) |
| `TS6_NICKNAME` | `${MUMBLE_BOT_USERNAME}` | Bot display name (`clientupdate`) |
| `TS6_CHANNEL` | `${MUMBLE_TARGET_CHANNEL}` | Channel to join (exact match, first hit + warning on dupes) |
| `TS6_CHANNEL_PASSWORD` | empty | Channel password (`cpw`) |
| `TS6_VOICE_HOST` / `TS6_VOICE_PORT` | `TS6_HOST` / `9987` | Voice client target (`:9987/udp`) |
| `TS6_SERVER_PASSWORD` | empty | Voice server password |
| `TS6_IDENTITY` | empty | Persisted voice identity (empty = generate once, then reuse printed value; fresh identities may need a security-level upgrade) |
| `TS6_BRIDGE_RX_PORT` / `TS6_BRIDGE_TX_PORT` | `5001` / `5002` | Localhost PCM ports (bridge→Python / Python→bridge) |
| `TS6_BRIDGE_TOKEN` | empty | Shared secret prefixing bridge UDP datagrams |

Query setup on the server:

```bash
TSSERVER_QUERY_SSH_ENABLED=1
TSSERVER_QUERY_ADMIN_PASSWORD=<== TS6_QUERY_PASSWORD>
# add the bot IP to query_ip_allowlist.txt or FloodError id 524 occurs
```

Voice bridge (see [bridge/ts-voice-bridge/README.md](bridge/ts-voice-bridge/README.md)):

```bash
cd bridge/ts-voice-bridge && npm install   # @honeybbq/teamspeak-client + @discordjs/opus (Node >= 20.19)
# Python BridgeSupervisor spawns `node index.js` automatically.
```

`?status` shows `Backend: mumble|teamspeak6` + `VoiceBridge: Connected/Down/N/A`.
Kill the bridge to verify degradation: text keeps working while voice reports `Down`.
`MUMBLE_BANDWIDTH` is Mumble-only (no-op on TS).

## Tests

```bash
python -m pytest tests/
python -m unittest tests.test_teamspeak_backend -v   # TS6: factory, normalize, music guard, bridge framing
```
