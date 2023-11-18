import json
import asyncio
import logging
import time

import cheshire_cat_api as ccat
from cheshire_cat_api.utils import Settings, WebSocketSettings

from telegram import Update
from telegram.ext import filters, ApplicationBuilder, ContextTypes, MessageHandler
from telegram.constants import ChatAction

T = 10

class CCatConnection:

    def __init__(self, user_id, out_queue: asyncio.Queue, ccat_url: str = "localhost", ccat_port: int = 1865) -> None:
        self.user_id = user_id

        # Get event loop
        self._loop = asyncio.get_running_loop()

        # Queue of the messages to send on telegram
        self._out_queue = out_queue
        
        ws_settings = WebSocketSettings(user_id=user_id)
        ccat_settings = Settings(
            base_url=ccat_url,
            port=ccat_port,
            ws=ws_settings
        )

        # Instantiate the Cheshire Cat client
        self.ccat = ccat.CatClient(
            settings=ccat_settings,
            on_message=self._ccat_message_callback,
            on_open=self._on_open,
            on_close=self._on_close
        )

        self.last_interaction = time.time()


    def _ccat_message_callback(self, message: str):
        # Websocket on_mesage callback

        message = json.loads(message)

        # Put the new message from the cat in the out queue
        # the websocket runs in its own thread
        # call_soon_threadsafe: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_soon_threadsafe
        #                       https://stackoverflow.com/questions/53669218/asyncio-queue-get-delay
        self._loop.call_soon_threadsafe(self._out_queue.put_nowait, (message, self.user_id))
    
    
    def _on_open(self):
        logging.info(f"WS connection with user `{self.user_id}` to CheshireCat opened")


    def _on_close(self, close_status_code: int, msg: str):
        logging.info(f"WS connection `{self.user_id}` to CheshireCat closed")
    

    def send(self, message: str, **kwargs):
        self.last_interaction = time.time()
        self.ccat.send(message=message, **kwargs)


class Meogram():

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

            # Start closing idle ws connection each T seconds
            self._loop.call_later(T, self._close_unactive_connections)

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

        voice_message_id = update.message.voice.file_id
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
            message="*[Voice Note]* But you can't hear.",
            meogram_voice=voice_message_id
        )


    def _close_unactive_connections(self):
            logging.info(msg="Closing inactive connections")

            t = time.time()

            marked_for_deletion = []
            for key, conn in self._connections.items():

                if conn.ccat.is_closed:
                    marked_for_deletion.append(key)
                    break

                if t - conn.last_interaction > 20:
                    # Close the connection as mark it for delete
                    conn.ccat.close()
                    marked_for_deletion.append(key)

            # Delete closed connections
            for user_id in marked_for_deletion:
                del self._connections[user_id]  

            # Scheduling the next running
            self._loop.call_later(T, self._close_unactive_connections)

