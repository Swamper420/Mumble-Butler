import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    from bot import MadnessBot
    bot = MadnessBot()
    bot.run()
