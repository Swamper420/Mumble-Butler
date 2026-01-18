# Mumble Butler (Obama)

A sophisticated, AI-powered Mumble bot designed to act as a digital butler for your server. It features real-time voice recognition, text-to-speech responses, LLM-driven conversation, and music/audio playback controls.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Mumble](https://img.shields.io/badge/mumble-1.4%2B-orange)

## 🌟 Features

* **🗣️ Voice-to-Text (STT):** Listens to users in a Mumble channel using `faster-whisper`.
* **🧠 AI Personality:** Powered by a local LLM (e.g., `qwen2.5-3b-instruct`) via `llama-cpp-python`.
* **🔊 Text-to-Speech (TTS):** Generates high-quality voice responses using `Kokoro-82M`.
* **🤖 Bot-to-Bot Control:** Acts as a voice interface for **[botamusique](https://github.com/azlux/botamusique)**. Speak commands to "Obama," and he translates them into text commands (`!play`, `!volume`) for the music bot.
* **🎤 Smart Recommendations:** Ask the bot to recommend music based on a vibe; it searches and queues the song automatically.
* **🔧 Extensive Configuration:** Easy-to-edit `config.py` for tweaking triggers, models, and paths.

## 🛠️ Prerequisites

* **Python 3.10+**
* **Mumble Server (Murmur)**
* **[Botamusique](https://github.com/azlux/botamusique):** **REQUIRED.** You must have `botamusique` running in the same channel. This bot handles the actual music playback, while "Obama" acts as the voice interface for it.
* **NVIDIA GPU (Recommended):** For `cuda` acceleration of Whisper and TTS models.
* **FFmpeg:** Installed and added to your system PATH.

## 📦 Installation

1.  **Clone the Repository**
    ```bash
    git clone [https://github.com/yourusername/mumble-butler.git](https://github.com/yourusername/mumble-butler.git)
    cd mumble-butler
    ```

2.  **Install Dependencies**
    It is recommended to use a virtual environment.
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: You may need to install `llama-cpp-python` with specific hardware acceleration flags depending on your GPU. Refer to their [documentation](https://github.com/abetlen/llama-cpp-python).)*

3.  **Download Models**
    * **LLM:** Download a GGUF model (e.g., `qwen2.5-3b-instruct-q4_k_m.gguf`) and place it in a `models/` directory.
    * **Kokoro:** The `Kokoro` pipeline will download required weights automatically on first run.

4.  **Configure FFmpeg**
    Ensure `ffmpeg` is accessible in your terminal.
    ```bash
    ffmpeg -version
    ```

## ⚙️ Configuration

Edit `config.py` to match your environment.

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SERVER_IP` | IP address of your Mumble server. | `"127.0.0.1"` |
| `SERVER_PORT` | Port of your Mumble server. | `64738` |
| `BOT_USERNAME` | The name the bot uses in Mumble. | `"Obama"` |
| `PASSWORD` | Server password (if applicable). | `"password"` |
| `TARGET_CHANNEL` | The channel the bot will join. | `"General"` |
| `ACTIVATION_KEYWORD` | Spoken word required to trigger the bot. | `"obama"` |
| `LLM_MODEL_PATH` | Path to your local GGUF model file. | `"models/..."` |

## 🚀 Usage

1.  **Start Botamusique:** Ensure your music bot is running and connected to the target channel.
2.  **Start Mumble Butler:**
    ```bash
    python main.py
    ```
3.  **Verify Connection:** Speak a command (e.g., *"Obama, play lo-fi hip hop"*). "Obama" should respond verbally and immediately send a `!yplay` text command to the channel, which `botamusique` will pick up.

## 🧩 How It Works

```mermaid
graph LR
    User(User via Voice) -->|Spoken Command| Butler(Mumble Butler)
    Butler -->|TTS Response| User
    Butler -->|Text Command !play| MusicBot(Botamusique)
    MusicBot -->|Audio Stream| MumbleServer
