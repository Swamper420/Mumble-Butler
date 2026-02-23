# Mumble Butler

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.10%2B-blue)]() [![Mumble](https://img.shields.io/badge/mumble-1.4%2B-orange)]()

A modern, extensible AI assistant for Mumble servers. **Mumble Butler** listens to voice commands, understands natural language using a local LLM, replies with synthesized speech, and **plays music natively** (no external bots required). It now replaces the old Botamusique integration entirely. Designed for privacy, performance, and ease of customization.

---

## 🧩 Core Capabilities

- **Speech‑to‑Text (STT)** – Real-time transcription using `faster-whisper`.
- **Conversational Intelligence** – Local GGUF models driven by `llama-cpp-python`.
- **Text‑to‑Speech (TTS)** – Natural replies via `Kokoro-82M`.
- **Built‑in Music Player** – Search/queue tracks from YouTube or local files, manage volume/queue/modes and hear audio directly from the bot.
- **Context‑Aware Recommendations** – Ask for a mood or genre and the bot queues matching tracks automatically.
- **Highly Configurable** – Behavior is controlled through `config.py`; no code changes required.

---

## 🚀 Quick Start

### Prerequisites

1. Python **3.10+**
2. Mumble server (Murmur) **1.4+**
3. FFmpeg installed and on `PATH` (used for decoding external audio sources)
4. `yt-dlp` available in the environment (used for YouTube searches and URLs)
5. (Optional) NVIDIA GPU & CUDA for accelerated inference

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
2. Speak a command, e.g. **“Obama, play lo-fi hip hop”**. The bot will respond vocally and stream the audio itself.

Below are some of the supported voice/chat commands:

- "play <query>" / "queue <query>" – add a song/search term to the queue
- "skip" / "next" – skip current track
- "stop" / "pause" / "resume" – control playback
- "volume <0‑100>" – set volume percentage
- "repeat 2" – repeat current track twice
- "mode autoplay|repeat|random|one-shot" – change queue behaviour
- Text equivalents are available with `?play`, `?skip`, `?volume`, etc.

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
| `LLM_MODEL_PATH`   | Path to local GGUF model                | `"models/..."`        |

---

## 📐 Architecture Overview

```mermaid
graph LR
    User[User (Voice)] -->|Audio| Butler[Mumble Butler]
    Butler -->|STT / NLU| LLM
    Butler -->|TTS| User
    Butler -->|Internal Player| MumbleServer
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

