import argparse
import threading
import time
import config

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api",
        action="store_true",
        help="Start bot runtime and force-enable LLM + voice HTTP APIs."
    )
    parser.add_argument(
        "--api-only",
        dest="api_only",
        action="store_true",
        help="Run only HTTP APIs (no Mumble bot connection)."
    )
    args = parser.parse_args()

    if args.api_only:
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
        if args.api:
            config.START_LLM_API_WITH_BOT = True
            config.START_VOICE_API_WITH_BOT = True
            print("INFO: '--api' enabled. Forcing LLM + voice HTTP APIs on with bot runtime.")
        from bot import MadnessBot
        bot = MadnessBot()
        bot.run()
