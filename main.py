import os
import logging
import asyncio
from dotenv import load_dotenv

from ccat_telegram_bot import CCatTelegramBot

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def main():
    bot = CCatTelegramBot(TOKEN)
    await bot.run()
    
if __name__ == "__main__":
    asyncio.run(main())