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

        # Used to store for each connection when the last typing action is sended
        self.last_typing_action = {}

        self._connections: Dict[str, CCatConnection] = {}

        # Create telegram application
        self.telegram: Application = ApplicationBuilder().token(telegram_token).build()

        # This handler open a connection to the cheshire cat for the user if it doesn't exist yet
        self.connect_to_ccat = MessageHandler(filters.ALL, self._open_ccat_connection)
        self.telegram.add_handler(self.connect_to_ccat)

        # Handlers to manage different types of messages after the connection to the cheshire cat is opened 
        # in the previous handler group
        self.text_message_handler =  MessageHandler(filters.TEXT & (~filters.COMMAND), self._text_handler)
        self.voice_message_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), self._voice_note_handler)
        self.document_message_handler = MessageHandler(filters.Document.ALL & (~filters.COMMAND), self._document_handler)

        self.telegram.add_handler(handler=self.document_message_handler, group=1)
        self.telegram.add_handler(handler=self.voice_message_handler, group=1)
        self.telegram.add_handler(handler=self.text_message_handler, group=1)
        self.telegram.add_handler(handler=self.document_message_handler, group=1)


    async def run(self):
        try:
            await self.telegram.initialize()
            await self.telegram.updater.start_polling(read_timeout=10)  
            await self.telegram.start()

            responce_loop = self._loop.create_task(self._out_queue_dispatcher())
            await responce_loop

        except asyncio.CancelledError:
            logging.info("STOPPING THE APPLICATION")
            await self.telegram.updater.stop()
            await self.telegram.stop()
        except Exception as e:
            logging.exception(f"Unexpectet exeption occured: {e}")
        finally:
            await self.telegram.shutdown()
            for connection in self._connections.values():
                if connection.ccat is not None:
                    connection.ccat.close()


    async def _open_ccat_connection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id

        if chat_id not in self._connections:
            self._connections[chat_id] = CCatConnection(
                    user_id=chat_id,
                    out_queue=self._out_queue,
                    ccat_url=self.ccat_url,
                    ccat_port=self.ccat_port
                )
            
        # waiting for websocket connection
        if not self._connections[chat_id].is_connected:
            await self._connections[chat_id].connect()

            # If the connection is not successful, message handling is interrupted
            if not self._connections[chat_id].is_connected:
                logging.warning("Interrupt handling this message, failed to connect to the Cheshire Cat")
                raise ApplicationHandlerStop
                        

    async def _text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        
        # Send mesage to the cat
        self._connections[chat_id].send(
            message=update.message.text, 
            meowgram = {
                "update": update.to_json()
            },
        )
        

    async def _voice_note_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        
        voice_message_file = await update.message.voice.get_file()
            
        # Send mesage to the cat
        self._connections[chat_id].ccat.send(
            message="*[Voice Note]* (You can't hear)",
            meowgram_voice=voice_message_file.file_path,
            meowgram = {
                "update": update.to_json()
            },
        )


    async def _document_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        pass


    async def _out_queue_dispatcher(self):
        while True:
            message, user_id = await self._out_queue.get()

            logging.debug(f"Message from {user_id}: {json.dumps(message, indent=4)}")

            try:
                if message["type"] == "chat":
                    # send the message in chat
                    await self._dispatch_chat_message(message=message, user_id=user_id)
                elif message['type'] == "chat_token":
                    # Send the chat action TYPING every 5 seconds 
                    # during the tokens streaming
                    await self._dispatch_chat_token(user_id)
            except Exception as e:
                logging.error(f"An error occurred sending a telegram message: {e}")


    async def _dispatch_chat_message(self, message, user_id):
        send_params = message.get("meowgram", {}).get("send_params", {})

        out_msg = {
            "chat_id": user_id,
            "text": message["content"],
            **send_params,
        }

        await self.telegram.bot.send_message(**out_msg)


    async def _dispatch_chat_token(self, user_id):
        t = time.time()

        if user_id not in self.last_typing_action:
            self.last_typing_action[user_id] = t - 5
            
        # Check elapsed time
        if t - self.last_typing_action[user_id] > 5:

            logging.info(f"Sending chat action Typing to user {user_id}")

            # Update the time of the last typing action
            self.last_typing_action[user_id] = t

            # Send the action
            await self.telegram.bot.send_chat_action(
                chat_id=user_id,
                action=ChatAction.TYPING
            )

