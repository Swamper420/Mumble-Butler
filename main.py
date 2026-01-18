import config
from bot import MadnessBot

if __name__ == "__main__":
    # Apply protocol fix
    config.patch_ssl()

    # Init and start
    bot = MadnessBot()
    bot.run()
