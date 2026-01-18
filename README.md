Mumble Butler 🤖

A highly configurable, AI-powered Mumble bot featuring local LLM processing, voice recognition, and text-to-speech.

The bot acts as a digital butler (default personality: "Obama") that listens to voice commands in a Mumble channel, transcribes audio using Whisper, generates intelligent responses using a local LLM, and controls audio playback.

Features

🎙️ Voice Activation: Listens for a configurable wake word (default: "Obama").

🧠 Local LLM: Integrates with llama.cpp to run GGUF models locally for private, smart interactions.

👂 Speech-to-Text: High-performance transcription using faster-whisper.

🗣️ Text-to-Speech: Modular TTS support (Kokoro/Voice module).

🎵 Music & Audio Control: Supports YouTube playback, local file playback, queue management, and volume control.

⚙️ Highly Configurable: Centralized config.py for easy editing of prompts, triggers, and connection settings.

Requirements

Python 3.10+

Mumble Server (Murmur)

FFmpeg (Must be installed and added to system PATH)

NVIDIA GPU (Highly recommended for Whisper and LLM inference)

Installation

Clone the repository

git clone [https://github.com/yourusername/mumble-butler.git](https://github.com/yourusername/mumble-butler.git)
cd mumble-butler


Install Dependencies

pip install pymumble-py3 faster-whisper llama-cpp-python
# Note: Install other dependencies required by your specific modules/ directory


Tip: For llama-cpp-python hardware acceleration, ensure you install the version matching your CUDA version.

Setup Models

LLM: Download a GGUF model (e.g., Qwen 2.5, Llama 3) and place it in the models/ directory.

Whisper: The bot will automatically download the required Whisper model on first run.

Configuration
Edit config.py to match your environment:

Update SERVER_IP, PORT, and PASSWORD.

Set the LLM_MODEL_PATH to your downloaded GGUF file.

Customize SYSTEM_PROMPT to change the bot's personality.

Usage

Voice Commands

Speak the Activation Keyword (e.g., "Obama") followed by your command:

Command Trigger

Action

Example

Play / Queue

Search and play music (YouTube)

"Obama, play Despacito"

Recommend

AI recommends a song based on mood

"Obama, recommend some 80s pop"

File / F

Play a local file by path/keyword

"Obama, file jazz"

Stop / Silence

Pause current audio

"Obama, stop"

Skip / Next

Skip to next track

"Obama, next"

Repeat

Repeat current track X times

"Obama, repeat 3"

Volume

Set volume (0-100)

"Obama, volume 50"

Forget

Wipe conversation memory

"Obama, forget everything"

(Conversational)

Ask any question

"Obama, what is the meaning of life?"

Text Commands (Chat)

Send these commands in the Mumble text chat:

?help - List available commands.

?listen - Toggle voice listening on/off.

?voice [name] - Change the TTS voice (e.g., ?voice bella).

?say [text] - Force the bot to say something.

?forget - Reset the AI's short-term memory.

Configuration Guide

The config.py file allows you to fine-tune the bot without touching code:

# Change the bot's personality
SYSTEM_PROMPT = "You are a pirate..."

# Modify Voice Triggers
VOICE_TRIGGERS = {
    'STOP': ["stop", "halt", "cease"],
    ...
}


Structure

bot.py: Core logic, Mumble callbacks, and threading.

brain.py: Handles LLM context, history, and generation.

config.py: Configuration constants.

modules/: Contains ears.py (Whisper), voice.py (TTS), and audio_buffer.py.
