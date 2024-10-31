import re
import os
import time
import json
import asyncio
import logging
import requests
import tempfile
import functools
import soundfile as sf

from enum import Enum
from typing import Dict

import ffmpeg
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application, 
    ApplicationBuilder,
    CallbackQueryHandler, 
    ContextTypes, 
    MessageHandler, 
    ApplicationHandlerStop, 
    filters,
    CommandHandler
)
from telegram.constants import ChatAction

from ccat_connection import CCatConnection

# Conversational Form State
class CatFormState(Enum):
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    WAIT_CONFIRM = "wait_confirm"
    CLOSED = "closed"


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

        self.delete_reply_markup = MessageHandler(filters.ALL, self._delete_reply_markup)
        self.telegram.add_handler(self.delete_reply_markup, group=3)

        self.form_inline_keyboard_handler = CallbackQueryHandler(self._form_handler)
        self.telegram.add_handler(handler=self.form_inline_keyboard_handler)

    async def run(self):
        # https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.run_polling
        # Initializing and starting the app

        await self.bot.set_my_commands(commands=[("/clear_chat", "Clear conversation history")])

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
                await connection.disconnect()

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
            logging.debug(f"Image found in message: {photo_path}")
        else:
            logging.debug("No image in the message.")

        # Invia messaggio al cat
        logging.debug("Sending message to CheshireCat")
        await self._connections[chat_id].send(
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
        await self._connections[chat_id].send(
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
        await self._connections[chat_id].send(
            message="*[Voice Note]* (You can't hear)",
            meowgram_voice=voice_message_file.file_path,
            meowgram = {
                "update": update.to_json()
            },
        )

    async def _document_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        pass

    async def _form_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        query = update.callback_query
        
        pattern = r"^form_(?P<form_name>[a-zA-Z0-9_]+)_(?P<action>confirm|cancel)$"
        match = re.match(pattern, query.data)

        if match:

            form_name = match.group('form_name')
            action = match.group("action")

            await self._connections[chat_id].send(
                message=f"[{action}]",
                meowgram={
                    "update": update.to_json(),
                    "form_action": {
                        "form_name": form_name,
                        "action": action
                    }
                },
            )

            await query.edit_message_reply_markup(reply_markup=None)
        
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
        meogram_params = message.get("meowgram", {})
        send_params = meogram_params.get("send_params", {})
        settings = meogram_params.get("settings", {
            "show_tts_text": False
        })

        active_form = meogram_params.get("active_form", None)
        reply_markup = None
        if active_form:

            form_state = active_form["state"]
            keyboard = []

            if form_state == CatFormState.WAIT_CONFIRM.value:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "Confirm",
                            callback_data=f"form_{active_form['name']}_confirm",
                        )
                    ]
                )

            if form_state != CatFormState.CLOSED.value:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "Cancel",
                            callback_data=f"form_{active_form['name']}_cancel",
                        )
                    ]
                )
            
            reply_markup = InlineKeyboardMarkup(keyboard)


        tts_url = message.get("tts", None)
        if tts_url:
            # Get audio file
            response = requests.get(tts_url)
            if response.status_code != 200:
                # If there is an error in retrieving the audio file, it sends a text message
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message["content"], 
                    reply_markup=reply_markup,
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
                    reply_markup=reply_markup,
                    **send_params
                )

                # Remove converted file
                os.remove(speech_file_ogg_path)

        else:
            # If there is no TTS URL, simply send a text message
            await self.bot.send_message(
                chat_id=user_id,
                text=message["content"], 
                reply_markup=reply_markup,
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
        message_id = update.message.message_id

        wipe_conversation = self._connections[user_id].api.memory.wipe_conversation_history
        
        await self._loop.run_in_executor(
            executor= None,
            func = functools.partial(wipe_conversation, _headers={"user_id": user_id})
        )
        max_messages_to_delete = 100
        message_ids = []

        # Collect IDs of messages to be deleted, up to max_messages_to_delete
        for message_id in range(message_id, message_id - max_messages_to_delete, -1):
            message_ids.append(message_id)

       
        await self.bot.delete_messages(user_id, message_ids)
        
    async def _delete_reply_markup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message_id = update.message.message_id - 1

        try:
            await self.bot.edit_message_reply_markup(
                chat_id=update.effective_chat.id, 
                message_id=message_id, 
                reply_markup=None
            )
        except BadRequest as e:
            logging.debug(f"[No reply markup to remove in previous message] {e.message}")
        else:
            logging.debug("Reply markup removed from previous message.")
