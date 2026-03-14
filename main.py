import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api",
        action="store_true",
        help="Run an HTTP API for direct LLM queries from external programs."
    )
    args = parser.parse_args()

    if args.api:
        from modules.llm_api import run_llm_api_server
        run_llm_api_server()
    else:
        from bot import MadnessBot
        bot = MadnessBot()
        bot.run()
