#!/usr/bin/env python3
"""Standalone TTS API Server for Mumble-Butler.

Runs the HTTP TTS API independently of the Mumble bot.
Auto-loads the Chatterbox API model (CHATTERBOX_API_MODEL) on startup
and automatically reloads on CUDA/GPU failures so the server remains functional.
"""

import sys
import os
import time
import signal
import argparse
import logging

import config
from modules.voice import Voice
from modules.web_server import BotWebServer, WebRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TTS_API_Server")

def main():
    parser = argparse.ArgumentParser(description="Standalone TTS API Server")
    parser.add_argument("--host", type=str, default=getattr(config, "WEB_SERVER_HOST", "0.0.0.0"), help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=getattr(config, "API_SERVER_PORT", 8081), help="Port to bind (default: 8081)")
    parser.add_argument("--model", type=str, default=getattr(config, "CHATTERBOX_API_MODEL", "https://huggingface.co/Finnish-NLP/Chatterbox-Finnish"), help="TTS API Model to auto-load")
    args = parser.parse_args()

    api_model = args.model
    logger.info("==================================================")
    logger.info("🗣️ Starting Standalone TTS API Server")
    logger.info(f"📍 Host: {args.host}:{args.port}")
    logger.info(f"📦 Auto-loading API Model: {api_model}")
    logger.info("==================================================")

    # 1. Auto-load the API model into Voice instance on startup
    try:
        voice = Voice(model_type=api_model)
        WebRequestHandler.fallback_voice = voice
        logger.info("✅ Voice engine & API model successfully pre-loaded into memory.")
    except Exception as e:
        logger.error(f"❌ Failed to auto-load TTS API model on startup: {e}")
        sys.exit(1)

    # 2. Start HTTP Web Server
    server = BotWebServer(bot_instance=None, host=args.host, port=args.port)
    server.start()

    running = True

    def signal_handler(sig, frame):
        nonlocal running
        logger.info(f"\nReceived signal {sig}. Shutting down Standalone TTS API Server...")
        running = False
        server.stop()
        logger.info("Bye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(f"🚀 TTS API Server ready and listening on http://{args.host}:{args.port}/api/tts")

    # Main loop keepalive
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

if __name__ == "__main__":
    main()
