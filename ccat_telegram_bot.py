import json
import asyncio
import requests
import tempfile

import cheshire_cat_api as ccat
from cheshire_cat_api.utils import Settings

from telegram import Update
from telegram.ext import filters, ApplicationBuilder, ContextTypes, MessageHandler, Updater

class CCatTelegramBot():

    def __init__(self, telegram_token: str, ccat_url: str = "localhost", ccat_port: int = 1865) -> None:
        # Queue of the messages to send on telegram
        self._out_queue = asyncio.Queue()

        self._loop = asyncio.get_event_loop()

        ccat_settings = Settings()

        ccat_settings.base_url = ccat_url
        ccat_settings.port = ccat_port

        self.ccat = ccat.CatClient(
            settings=ccat_settings,
            on_message= self._ccat_message_callback
        )

        self.telegram = ApplicationBuilder().token(telegram_token).build()

        self.text_message_handler =  MessageHandler(filters.TEXT & (~filters.COMMAND), self._text_handler)
        self.voice_message_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), self._voice_note_handler)

        self.telegram.add_handler(self.text_message_handler)
        self.telegram.add_handler(self.voice_message_handler)

        self.sensory_url = "http://localhost:8500"


    async def run(self):
        async with self.telegram:
            await self.telegram.initialize()
            await self.telegram.start()
            await self.telegram.updater.start_polling()

            while True:
                msg = await self._out_queue.get()
                msg = json.loads(msg)
                    
                await self.telegram.bot.send_message(
                    chat_id=msg["user_id"], 
                    text=msg["content"]
                )         


    def _ccat_message_callback(self,message: str):
        # Websocket on_mesage callback

        # Put the new message from the cat in the out queue
        self._loop.call_soon_threadsafe(self._out_queue.put_nowait, message)
        # call_soon_threadsafe: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_soon_threadsafe
        #                       https://stackoverflow.com/questions/53669218/asyncio-queue-get-delay


    async def _text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Send mesage to the cat
        self.ccat.send(message=update.message.text, user_id=update.effective_chat.id)


    async def _voice_note_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        userd_id = update.effective_chat.id

        # Extract audio bytes as bytearray
        voice_file = await update.message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray(connect_timeout=10)

        try:
            # Get text from audio
            text = self._stt(file_name=update.message.voice.file_id, audio_bytes=audio_bytes)

            # Send mesage to the cat
            self.ccat.send(message=text, user_id=userd_id)
        except:
            await self._out_queue.put({
                "content": "I can't listen at the moment, could you send a text?",
                "user_id": userd_id
            })


    def _stt(self, file_name: str, audio_bytes: bytearray): 

        header = {
            'accept': 'application/json',
        }
        files = {
            'audio': (file_name, audio_bytes, "video/ogg")
        }
        
        response = requests.post(f"{self.sensory_url}/stt", files=files, headers=header)
        response = response.json()
        
        return response["text"]
    

    def _tts(self, text: str):
         
        header = {
            'accept': 'application/json',
        }
        params = {
            'text': text
        }
        
        response = requests.post(f"{self.sensory_url}/tts", params=params, headers=header)

        tmp_file_audio = tempfile.NamedTemporaryFile(suffix=".wav")
        tmp_file_audio.write(response.content)
        # song = AudioSegment.from_ogg(tmp.file.name)
        # song.export("prova.wav", format="wav")
        # TODO: try to handle .ogg directly

        return tmp_file_audio
        