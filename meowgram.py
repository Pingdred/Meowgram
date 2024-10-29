import os
import time
import json
import asyncio
import logging
import requests
import tempfile
import soundfile as sf

from typing import Dict

import ffmpeg
from telegram import Update, Bot
from telegram.ext import (
    Application, 
    ApplicationBuilder, 
    ContextTypes, 
    MessageHandler, 
    ApplicationHandlerStop, 
    filters,
    CommandHandler
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
        self.bot: Bot = self.telegram.bot

        # This handler open a connection to the cheshire cat for the user if it doesn't exist yet
        self.connect_to_ccat = MessageHandler(filters.ALL, self._open_ccat_connection)
        # Using default group
        self.telegram.add_handler(self.connect_to_ccat)

        # Handlers to manage different types of messages after the connection to the cheshire cat is opened 
        # in the previous handler group
        self.text_message_handler =  MessageHandler(filters.TEXT & (~filters.COMMAND), self._text_handler)
        self.photo_message_handler =  MessageHandler(filters.PHOTO & (~filters.COMMAND), self._photo_handler)
        self.voice_message_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), self._voice_note_handler)
        self.document_message_handler = MessageHandler(filters.Document.ALL & (~filters.COMMAND), self._document_handler)
        self.clear_chat_history_handler = CommandHandler("clear_chat", self._clear_chat_history)

        self.telegram.add_handler(handler=self.document_message_handler, group=1)
        self.telegram.add_handler(handler=self.voice_message_handler, group=1)
        self.telegram.add_handler(handler=self.text_message_handler, group=1)
        self.telegram.add_handler(handler=self.photo_message_handler, group=1)
        self.telegram.add_handler(handler=self.document_message_handler, group=1)
        self.telegram.add_handler(handler=self.clear_chat_history_handler,group=1)

    async def run(self):
        # https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.run_polling
        # Initializing and starting the app

        await self.bot.set_my_commands(commands=[("/clear_chat", "Clear Cheshire Cat conversation history")])

        try:
            await self.telegram.initialize()
            await self.telegram.updater.start_polling(read_timeout=10)  
            await self.telegram.start()
            
            # Start main loop
            responce_loop = self._loop.create_task(self._out_queue_dispatcher())
            await responce_loop

        except asyncio.CancelledError:
            # Cancelled error from _out_queue_dispatcher
            logging.info("STOPPING THE APPLICATION")
            # Stop telegram updater
            await self.telegram.updater.stop()
            # Stop telegram bot application
            await self.telegram.stop()
        except Exception as e:
            logging.exception(f"Unexpectet exeption occured: {e}")
        finally:
            # Shutdown telergram bot application
            await self.telegram.shutdown()
            # Close open ws connections
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

        # Controlla se c'è una foto nel messaggio
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
            photo_file = await self.bot.get_file(photo_id)
            photo_path = photo_file.file_path
        else:
            photo_path = None

        # Logging del percorso del file foto se presente
        if photo_path:
            logging.error(photo_path)
        else:
            logging.error("Nessuna foto presente nel messaggio.")

        # Invia messaggio al cat
        self._connections[chat_id].send(
            message=update.message.text if update.message.text else "",
            meowgram={
                "update": update.to_json()
            },
            image=photo_path
        )

    async def _photo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id

        photo_id = update.message.photo[-1].file_id
        photo_file = await self.bot.get_file(photo_id)
        photo_path = photo_file.file_path

        # Invia messaggio al cat
        self._connections[chat_id].send(
            message=update.message.caption if update.message.caption else "",
            meowgram={
                "update": update.to_json()
            },
            image=photo_path
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
        settings = message.get("meowgram", {}).get("settings", {
            "show_tts_text": False
        })

        tts_url = message.get("tts", None)
        if tts_url:
            # Get audio file
            response = requests.get(tts_url)
            if response.status_code != 200:
                # If there is an error in retrieving the audio file, it sends a text message
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message["content"], 
                    **send_params
                )
                return

            with tempfile.NamedTemporaryFile() as speech_file:
                # Write the content of the response to the temporary file
                speech_file.write(response.content)

                # Convet audio to telegram voice note fromat
                speech_file_ogg_path = await self._loop.run_in_executor(None, self.convert_audio_to_voice, speech_file.name)

                # Check if converted file exists
                if not os.path.exists(speech_file_ogg_path):
                    return

                # Send voice note
                await self.bot.send_voice(
                    chat_id=user_id,
                    voice=open(speech_file_ogg_path, "rb"),
                    duration=sf.info(speech_file_ogg_path).duration,
                    caption=message["content"] if settings["show_tts_text"] else None,
                    filename=speech_file_ogg_path,
                    **send_params
                )

                # Remove converted file
                os.remove(speech_file_ogg_path)

        else:
            # If there is no TTS URL, simply send a text message
            await self.bot.send_message(
                chat_id=user_id,
                text=message["content"], 
                **send_params
            )

    def convert_audio_to_voice(self, input_path: str) -> str:
        # https://stackoverflow.com/questions/56448384/telegram-bot-api-voice-message-audio-spectrogram-is-missing-a-bug
        logging.info("Convert audio file to Telegram voice note format")
        output_path = os.path.splitext(input_path)[0] + "_converted.ogg"
        (
            ffmpeg.input(input_path)
            .output(output_path, codec="libopus", audio_bitrate="32k", vbr="on", compression_level=10, frame_duration=60, application="voip")
            .run()
        )
        return output_path

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
            await self.bot.send_chat_action(
                chat_id=user_id,
                action=ChatAction.TYPING
            )

    async def _clear_chat_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_chat.id

        self._connections[user_id].ccat.memory.wipe_conversation_history(_headers={"user_id":user_id})

        await self.bot.send_message(
            chat_id=user_id,
            text="Deleted chat memory..."
        )
