import argparse
import threading
import time

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api",
        action="store_true",
        help="Run HTTP APIs for direct LLM queries and voice transcription."
    )
    args = parser.parse_args()

    if args.api:
        from modules.llm_api import create_llm_api_server
        from modules.voice_api import create_voice_api_server

        llm_server = create_llm_api_server()
        voice_server = create_voice_api_server()
        threading.Thread(target=llm_server.serve_forever, daemon=True).start()
        threading.Thread(target=voice_server.serve_forever, daemon=True).start()

        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            llm_server.shutdown()
            voice_server.shutdown()
            llm_server.server_close()
            voice_server.server_close()
    else:
        from bot import MadnessBot
        bot = MadnessBot()
        bot.run()
