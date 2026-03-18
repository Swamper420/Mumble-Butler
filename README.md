# Mumble Butler

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.10%2B-blue)]() [![Mumble](https://img.shields.io/badge/mumble-1.4%2B-orange)]()

A modern, extensible AI assistant for Mumble servers. **Mumble Butler** listens to voice commands, understands natural language using a local LLM, replies with synthesized speech, and can **control music playback through botamusique commands**. Designed for privacy, performance, and ease of customization.

---

## 🧩 Core Capabilities

- **Speech‑to‑Text (STT)** – Real-time transcription using `faster-whisper`.
- **Conversational Intelligence** – Local GGUF models driven by `llama-cpp-python`.
- **Text‑to‑Speech (TTS)** – Natural replies via `Kokoro-82M`.
- **Botamusique Music Control** – Forward search, queue, playback, volume, and mode commands to a botamusique bot in the same Mumble channel.
- **Context‑Aware Recommendations** – Ask for a mood or genre and the bot queues matching tracks automatically.
- **Highly Configurable** – Behavior is controlled through `config.py`; no code changes required.

---

## 🚀 Quick Start

### Prerequisites

1. Python **3.10+**
2. Mumble server (Murmur) **1.4+**
3. A botamusique bot in the same Mumble channel for music playback
4. (Optional) NVIDIA GPU & CUDA for accelerated inference

### Installation

```bash
git clone https://github.com/Swamper420/Mumble-Butler.git
cd Mumble-Butler
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> 🗂️ Place your GGUF model (e.g. `qwen2.5-3b-instruct-q4_k_m.gguf`) under `models/`. Kokoro weights download automatically on first execution.

### Configuration

Open `config.py` and adjust values to match your environment. Example:

```python
SERVER_IP = "127.0.0.1"
SERVER_PORT = 64738
BOT_USERNAME = "Obama"
PASSWORD = "password"
TARGET_CHANNEL = "General"
ACTIVATION_KEYWORD = "obama"
LLM_MODEL_PATH = "models/qwen2.5-3b-instruct-q4_k_m.gguf"
```

Additional options control logging, device selection, and model parameters.

### Running

1. Launch the assistant:
   ```bash
   python main.py
   ```
   This starts the normal Mumble bot runtime **and** local HTTP APIs for LLM + voice transcription by default.
   If your `config.py` disables those API flags, run `python main.py --api` to force-enable both API servers with the bot runtime.
2. Speak a command, e.g. **“Obama, play lo-fi hip hop”**. The bot will forward the matching botamusique command into Mumble chat.

Below are some of the supported voice/chat commands:

- "play <query>" / "queue <query>" – forward a botamusique search command
- "skip" / "next" – skip current track
- "stop" / "pause" / "resume" – control playback
- "volume <0‑100>" – set volume percentage
- "repeat 2" – repeat current track twice
- "mode autoplay|repeat|random|one-shot" – change queue behaviour
- "shut up" / "be quiet" – stop the bot from listening
- Text equivalents are available with `?play`, `?now`, `?queue`, `?skip`, `?volume`, etc.

### External APIs (LLM + Voice Recognition)

When the bot is running normally (`python main.py`), both APIs are available at the same time.

You can also run API-only mode (without connecting to Mumble):

```bash
python main.py --api-only
```

Default API settings are in `config.py`:
- `LLM_API_HOST` (default `127.0.0.1`)
- `LLM_API_PORT` (default `8080`)
- `LLM_API_DEFAULT_MAX_TOKENS` (default `650`)
- `VOICE_API_HOST` (default `127.0.0.1`)
- `VOICE_API_PORT` (default `8081`)

The API uses its own system prompt (`API_SYSTEM_PROMPT`) that encourages detailed, thorough answers, while the Mumble bot uses `SYSTEM_PROMPT` which keeps voice responses short and concise. Both prompts are configurable in `config.py`.

LLM example request:

```bash
curl -X POST http://127.0.0.1:8080/query \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Give me a short summary of Mumble Butler","max_tokens":120}'
```

Health check:

```bash
curl http://127.0.0.1:8080/health
```

Voice transcription example request (`pcm_base64` must be 48kHz mono 16-bit PCM bytes):

```bash
curl -X POST http://127.0.0.1:8081/transcribe \
  -H "Content-Type: application/json" \
  -d '{"pcm_base64":"<base64-encoded-raw-pcm>"}'
```

---

## ⚙️ Configuration Reference

| Setting            | Description                             | Default                 |
|--------------------|-----------------------------------------|-------------------------|
| `SERVER_IP`        | Mumble server address                   | `"127.0.0.1"`         |
| `SERVER_PORT`      | Mumble server port                      | `64738`                |
| `BOT_USERNAME`     | Username used by the bot                | `"Obama"`             |
| `PASSWORD`         | Server password (if any)                | `"password"`          |
| `TARGET_CHANNEL`   | Channel to join                         | `"General"`           |
| `ACTIVATION_KEYWORD` | Word that activates the bot            | `"obama"`             |
| `SHUTUP_KEYWORDS`  | Phrases that silence the bot            | `["shut up", ...]`   |
| `SYSTEM_PROMPT`    | Bot system prompt (short responses)     | *(see config.py)*    |
| `API_SYSTEM_PROMPT`| API system prompt (detailed responses)  | *(see config.py)*    |
| `LLM_MODEL_PATH`   | Path to local GGUF model                | `"models/..."`        |

---

## 📐 Architecture Overview

```mermaid
graph LR
    User[User (Voice)] -->|Audio| Butler[Mumble Butler]
    Butler -->|STT / NLU| LLM
    Butler -->|TTS| User
    Butler -->|Botamusique Commands| MumbleServer
```

---

## 📁 Project Layout

```
.
├── bot.py
├── config.py
├── main.py
├── utils.py
├── handlers/
├── models/
└── modules/
```

---

## 🤝 Contributing

Contributions, enhancements, and bug reports are very welcome. Please open an issue or submit a pull request.

## 📬 Support

For questions or assistance, use GitHub Discussions or open an issue in the repository.

---

## 🛡️ License

This project is licensed under the [MIT License](LICENSE).
