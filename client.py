import logging
import asyncio
import json
from telegram import Update
from telegram.ext import filters, ApplicationBuilder, ContextTypes, MessageHandler, Updater
import cheshire_cat_api as ccat

import requests

cc_responses = asyncio.Queue()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def main():

    cat_client = ccat.CatClient() 

    loop = asyncio.get_event_loop()

    def send_cc_answer(message: str):
        loop.call_soon_threadsafe(cc_responses.put_nowait, message)

    cat_client.on_message = send_cc_answer

    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cat_client.send(message=update.message.text, user_id=update.effective_chat.id)

    async def voice_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        voice_file = await update.message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray(connect_timeout=10)

        header = {
            'accept': 'application/json',
        }
        files = {
            'audio': (update.message.voice.file_id, audio_bytes, "video/ogg")
        }
        
        response = requests.post("http://127.0.0.1:8000/stt", files=files, headers=header)
        response = response.json()

        print(response["text"])

        cat_client.send(message=response["text"], user_id=update.effective_chat.id)

    application = ApplicationBuilder().token("6431169895:AAF2Uomgfa6RvqNtpSFeAPSmVVi42rjbHCs").build()

    message_text_handler =  MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler)
    message_voice_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), voice_note_handler)
    application.add_handler(message_text_handler)
    application.add_handler(message_voice_handler)
    
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        while True:
            msg = await cc_responses.get()
            msg = json.loads(msg)
            await application.bot.send_message(
                chat_id=msg["user_id"], 
                text=msg["content"]
            )

if __name__ == "__main__":
    asyncio.run(main())