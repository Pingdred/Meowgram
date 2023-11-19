import os
import logging
import asyncio
from dotenv import load_dotenv

from meowgram import Meogram

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

CCAT_URL = os.getenv("CHESHIRE_CAT_URL", "localhost")
CCAT_PORT = os.getenv("CHESHIRE_CAT_PORT", "1865")

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def main():
    bot = Meogram(
            telegram_token=TOKEN,
            ccat_url=CCAT_URL,
            ccat_port=CCAT_PORT                  
        )
    await bot.run()
    
if __name__ == "__main__":
    asyncio.run(main())