import os
import logging
import asyncio

from colorlog import ColoredFormatter
from dotenv import load_dotenv

from meowgram import Meowgram

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

CCAT_URL = os.getenv("CHESHIRE_CAT_URL", "localhost")
CCAT_PORT = os.getenv("CHESHIRE_CAT_PORT", "1865")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Create a colored formatter
formatter = ColoredFormatter(
    fmt="%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S',
    style='%',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'white,bg_red',
    },
    reset=True
)

# Create a stream handler and set the formatter
ch = logging.StreamHandler()
ch.setFormatter(formatter)

# Add the handler to the root logger
logging.getLogger().addHandler(ch)

# Set the logging level
logging.getLogger().setLevel(LOG_LEVEL)

async def main():
    bot = Meowgram(
            telegram_token=TOKEN,
            ccat_url=CCAT_URL,
            ccat_port=CCAT_PORT                  
        )
    await bot.run()
    
if __name__ == "__main__":
    asyncio.run(main())