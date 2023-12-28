import time
import json
import asyncio
import logging

from typing import Dict

from telegram import Update
from telegram.ext import (
    Application, 
    ApplicationBuilder, 
    ContextTypes, 
    MessageHandler, 
    ApplicationHandlerStop, 
    filters
)
from telegram.constants import ChatAction

from ccat_connection import CCatConnection


class Meowgram():

    def __init__(self, telegram_token: str, ccat_url: str = "localhost", ccat_port: int = 1865) -> None:

        self.ccat_url = ccat_url
        self.ccat_port = ccat_port

        self._loop = asyncio.get_running_loop()

        # Queue of the messages to send on telegram
        self._out_queue = asyncio.Queue()

        self._connections = {}

        # Create telegram application
        self.telegram = ApplicationBuilder().token(telegram_token).build()

        # Create messages handlers
        self.text_message_handler =  MessageHandler(filters.TEXT & (~filters.COMMAND), self._text_handler)
        self.voice_message_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), self._voice_note_handler)

        # Add handlers to telegram application
        self.telegram.add_handler(self.text_message_handler)
        self.telegram.add_handler(self.voice_message_handler)


    async def run(self):
        try:
            await self.telegram.initialize()
            await self.telegram.updater.start_polling(read_timeout=10)  
            await self.telegram.start()

            responce_loop = self._loop.create_task(self._send_messages())
            await responce_loop

        except asyncio.CancelledError:
            logging.info("STOPPING THE APPLICATION")
            await self.telegram.updater.stop()
            await self.telegram.stop()
        finally:
            await self.telegram.shutdown()
            for connection in self._connections.values():
                connection.ccat.close()


    async def _send_messages(self):

        # Used to store for each connection when the last typing action is sended
        last_typing_action = {}

        while True:
            message, user_id = await self._out_queue.get()

            try:
                if message["type"] == "chat":
                    # send the message in chat
                    await self.telegram.bot.send_message(
                        chat_id=user_id,
                        text=message["content"],
                    )
                elif message['type'] == "chat_token":
                    # Send the chat action TYPING every 5 seconds 
                    # during the tokens streming
                    t = time.time()

                    if user_id not in last_typing_action:
                        last_typing_action[user_id] = t - 5
                        
                    # Check elapsed time
                    if t - last_typing_action[user_id] > 5:

                        logging.log(level=logging.INFO, msg=f"Sending chat action Typing to user {user_id}")

                        # Update the time of the last typing action
                        last_typing_action[user_id] = t

                        # Send the action
                        await self.telegram.bot.send_chat_action(
                            chat_id=user_id,
                            action=ChatAction.TYPING
                        )
            except Exception as e:
                logging.error(f"An error occurred sending a telegram message: {e}")


    async def _text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id

        # Open a ws connection for the user if non exists
        if chat_id not in self._connections:
            self._connections[chat_id] = CCatConnection(
                    user_id=chat_id,
                    out_queue=self._out_queue,
                    ccat_url=self.ccat_url,
                    ccat_port=self.ccat_port
                )

        # Send mesage to the cat
        self._connections[chat_id].send(message=update.message.text)
        

    async def _voice_note_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        voice_message_file = await update.message.voice.get_file()
        chat_id = update.effective_chat.id

        if chat_id not in self._connections:

            self._connections[chat_id] = CCatConnection(
                    user_id=chat_id,
                    out_queue=self._out_queue,
                    ccat_url=self.ccat_url,
                    ccat_port=self.ccat_port
                )
            
        # Send mesage to the cat
        self._connections[chat_id].ccat.send(
            message="*[Voice Note]* (You can't hear)",
            meowgram_voice=voice_message_file.file_path
        )









