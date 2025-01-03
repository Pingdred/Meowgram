import os
import logging
import asyncio

from colorlog import ColoredFormatter
from dotenv import load_dotenv

from telegram.bot import MeowgramBot

def setup_logging(log_level: str = "INFO") -> logging.Logger:
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

    logger = logging.getLogger()

    # Add the handler to the root logger
    logger.addHandler(ch)

    # Set the logging level
    logger.setLevel(log_level)

    return logger

async def main():
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO")

    # Setup the logging
    logger = setup_logging(log_level)

    bot = MeowgramBot(
        api_id=os.getenv("API_ID"),
        api_hash=os.getenv("API_HASH"),
        bot_token=os.getenv("BOT_TOKEN"),
        cat_url=os.getenv("CHESHIRE_CAT_URL", "localhost"),
        cat_port=os.getenv("CHESHIRE_CAT_PORT", "1865")
    )
    
    try:
        await bot.run()
    except Exception as e:
        logger.error(f"Error during bot execution: {e}")
    
  
if __name__ == "__main__":
    asyncio.run(main())