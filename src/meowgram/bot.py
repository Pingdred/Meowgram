import os
import re
import time
import logging
import asyncio
import tempfile
import requests
from typing import Dict

from telethon import TelegramClient, Button
from telethon.events import NewMessage, CallbackQuery, StopPropagation
from telethon.tl.types import BotCommand, BotCommandScopeDefault, Message
from telethon.tl.functions.bots import SetBotCommandsRequest
from cheshire_cat.client import CheshireCatClient

from meowgram.madia_handlers import handle_unsupported_media, handle_chat_media, handle_file
from utils import audio_to_voice, CatFormState, clean_code_blocks, clear_chat_history, build_base_cat_message

class MeowgramBot:

    def __init__(
        self, api_id: str, api_hash: str, bot_token: str, cat_url: str, cat_port: int
    ):
        self.client = TelegramClient('meowgram_bot', api_id, api_hash)
        self.bot_token = bot_token
        self.set_telegram_handlers()

        self.cat_url = cat_url
        self.cat_port = cat_port
        self.cat_connections: Dict[int, CheshireCatClient] = {}
        self.last_typing_action = {}
        
        self.logger = logging.getLogger(__name__)

    # SECTION: Telegram event handlers

    async def command_handler(self, event: CallbackQuery.Event):
        """Handle commands"""
        command = event.message.text
        try:
            match command:
                case "/start":
                    await event.reply("Welcome to Meowgram! How can I help you today?")

                case "/clear":
                    await clear_chat_history(self, event)
        except Exception as e:
            self.logger.error(f"An error occurred handling the command {command}: {e}")
        finally:
            raise StopPropagation

    async def message_handler(self, event: NewMessage.Event):
        """
        Main handler for incoming Telegram messages.

        Args:
            meowgram: The main bot instance with necessary methods.
            event: The incoming Telegram event containing the message.

        Note:
            This is the hierarchy of the message media types:
        """

        #  Message
        #     ├── text                                    Text content of the message (can contain only text or a caption)
        #     └── media                                   Media content attached to the message (if present)
        #         ├── photo                               Image sent as a photo
        #         ├── document                            Generic file content with extended attributes (can include various file types)
        #         │   ├── video                           Video content with thumbnail and duration
        #         │   │   └── video_note                  Round video message (usually 640x640)
        #         │   ├── audio                           Audio file with metadata (title, performer)
        #         │   │   └── voice                       Voice message recording
        #         │   ├── sticker                         Image or animation sticker
        #         │   │   ├── image/webp                  Image sticker (WebP format)
        #         │   │   ├── video/webm                  Video sticker (WebM format)
        #         │   │   └── application/x-tgsticker     Animated sticker (TGSticker format)
        #         │   ├── gif                             Animated image (GIF)
        #         │   │── file                            Generic file pdf, txt, etc.
        #         ├── contact                             Shared contact information
        #         ├── geo                                 Geographic coordinates (latitude and longitude)
        #         │   └── venue                           Location with title and address
        #         ├── poll                                Interactive poll
        #         ├── web_preview                         Webpage preview (link preview)
        #         ├── game                                Telegram game (interactive game)
        #         ├── invoice                             Payment invoice (Telegram Payments)
        #         └── dice                                Animated emoji/dice (used for sending dynamic emojis or dice)


        # 1. Check for unsupported media types that currenty are: 
        #   - GIFs, 
        #   - video/video_note, 
        #   - polls,
        #   - contacts, 
        #   - geo/venues,
        #   - video/animated stickers
        #
        # 2. Check for media types that can be sent in a chat: 
        #   - photos, 
        #   - voice note,
        #   - image stickers
        #
        # 3. Send the document to the Rabbit Hole to ingest it 
        #    the affected document types are:
        #   - audio files, (not voice notes)
        #   - generic files,

        user_id = event.sender_id
        cat_client: CheshireCatClient = await self.ensure_cat_connection(user_id)
        if not cat_client:
            return

        message: Message = event.message

        # If no media is present, send the text message directly.
        if not message.media:
            base_msg = build_base_cat_message(event)
            base_msg["text"] = message.text

            await cat_client.send_message(base_msg)
            return

        if msg := await handle_unsupported_media(event) or await handle_chat_media(event):
            # Add the caption associated with the media if present.
            if message.text:
                msg["text"] = message.text

            await cat_client.send_message(msg)
            return

        # Send every other media down the Rabbit Hole
        # document is checked last as it's the most generic media type
        if message.document:
            # TODO: Handle caption for document
            await handle_file(event, cat_client)

    async def form_action_handler(self, event: CallbackQuery.Event):
        """Handle form actions"""
        user_id = event.sender_id

        cat_client = await self.ensure_cat_connection(user_id)
        if not cat_client:
            return

        query = event.data.decode("utf-8")

        pattern = r"^form_(?P<form_name>[a-zA-Z0-9_]+)_(?P<action>confirm|cancel)$"
        match = re.match(pattern, query)

        if not match:
            return


        form_name = match.group('form_name')
        action = match.group("action")

        message = build_base_cat_message(event)
        message["text"] = action

        form_action = {
            "form_name": form_name,
            "action": action #{}, # No information are needed for form actions
        }
        message["form_action"] = form_action

        await cat_client.send_message(message)

        await event.edit(buttons=None)


    # SECTION: Bot initialization

    def set_telegram_handlers(self):
        """Setup event handlers"""

        # Handler for commands
        self.client.add_event_handler(
            self.command_handler, 
            NewMessage(pattern=r"/.*")
        )

        # Handler for messages
        self.client.add_event_handler(
            self.message_handler,
            NewMessage
        )

        # Handler for form actions
        self.client.add_event_handler(
            self.form_action_handler,
            CallbackQuery(pattern=r"form_.*"),
        )

    async def set_commands(self):
        # Delete all commands
        await self.client(SetBotCommandsRequest(scope=BotCommandScopeDefault(), lang_code='', commands=[]))

        # Set new commands
        commands = [
            BotCommand(command="clear", description="Clear chat history"),
        ]
        await self.client(SetBotCommandsRequest(scope=BotCommandScopeDefault() ,lang_code='', commands=commands))

    # SECTION: Bot lifecycle

    async def run(self):
        """Start bot with unified message handler"""        
        try:
            # Start the bot
            await self.client.start(bot_token=self.bot_token)

            # Set the bot commands
            await self.set_commands()

            self.logger.info("Bot started and listening")

            # Run the bot until it is disconnected
            await self.client.disconnected
        except asyncio.CancelledError:
            self.logger.info("Safely shutting down bot")
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Cleanup bot resources"""
        # Close the client
        await self.client.disconnect()

        # Close all Cheshire Cat connections
        self.logger.info("Closing Cheshire Cat connections")
        for _, cat_client in self.cat_connections.items():
            await cat_client.disconnect()
    
    # SECTION: Cheshire Cat connection management

    async def ensure_cat_connection(self, user_id: int) -> CheshireCatClient | None:
        """
        Ensures there is an active connection to Cheshire Cat for the user.
        If not, creates a new one.
        """

        cat_client = self.cat_connections.get(user_id)

        # Create a new connection if one does not exist
        if not cat_client:
            cat_client = CheshireCatClient(
                self.cat_url,
                self.cat_port,
                user_id,
                lambda msg: self.dispatch_cat_message(user_id, msg)
            )
            # Store the connection in the dictionary
            self.cat_connections[user_id] = cat_client   
      
        # Open a new connection if the WebSocket is closed
        if cat_client.ws is None or cat_client.ws.closed:

            if not (await cat_client.connect()):
                self.logger.error(f"Failed to connect to Cheshire Cat for user {user_id}")
                await self.client.send_message(user_id, "Failed to connect to Cheshire Cat. Please try again later.")
                return None
                
        return self.cat_connections[user_id]

    # SECTION: Incoming Cheshire Cat message handling

    async def dispatch_cat_message(self, user_id: int, message: dict):
        """
        Dispatches a cat message to the appropriate handler based on the message type.

        Args:
            user_id (int): The ID of the user sending the message.
            message (dict): The message to be dispatched. Must contain a "type" key.

        Message Types:
            - "chat": Calls the handle_chat_message method.
            - "chat_token": Calls the handle_chat_token method.
        """

        match message["type"]:
            case "chat":
                await self.handle_chat_message(user_id, message)
            case "chat_token":
                await self.handle_chat_token(user_id)
            case "error":
                self.logger.error(f"Error message received from Cheshire Cat: {message}")
                await self.client.send_message(user_id, f"An error occurred while processing your request: {message}")
            case "notification":
                pass           
        
    async def handle_chat_message(self, user_id: int, message: str):
        # Extract Meowgram-specific parameters if present
        meowgram_params = message.get("meowgram", {})
        send_params = meowgram_params.get("send_params", {})
        settings = meowgram_params.get("settings", {"show_tts_text": False})
        
        # Handle form buttons
        buttons = None
        active_form = meowgram_params.get("active_form")
        if active_form:
            form_state = active_form["state"]
            button_list = []
            
            if form_state == CatFormState.WAIT_CONFIRM.value:
                button_list.append([
                    Button.inline("Confirm", 
                        data=f"form_{active_form['name']}_confirm")
                ])
            
            if form_state != CatFormState.CLOSED.value:
                button_list.append([
                    Button.inline("Cancel",
                        data=f"form_{active_form['name']}_cancel")
                ])
            
            buttons = button_list if button_list else None

        # Handle TTS
        tts_url = message.get("tts")
        if tts_url:
            response = requests.get(tts_url)
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(response.content)
                    voice_path = await asyncio.to_thread(audio_to_voice, tmp.name)
                    
                    caption = message["text"] if settings["show_tts_text"] else None
                    await self.client.send_file(
                        user_id,
                        voice_path,
                        voice_note=True,
                        caption=caption,
                        buttons=buttons,
                        **send_params
                    )
                    os.remove(voice_path)
                    os.remove(tmp.name)
                    return
                
        # Remove language specification from code blocks
        text = clean_code_blocks(message["text"])

        # Send regular message
        await self.client.send_message(
            user_id,
            text,
            buttons=buttons,
            **send_params
        )
       
    async def handle_chat_token(self, user_id: int, seconds: int = 5): 
        current_time = time.time()  
        # Get the time of the last typing action, or default to the current time minus the delay
        last_typing_action = self.last_typing_action.get(user_id, current_time - seconds)  
        
        # If the user has sent a message too recently, skip the typing action
        if current_time - last_typing_action < seconds:
            self.logger.debug(f"Skipping chat action Typing to user {user_id}")
            return

        # Update the time of the last typing action
        self.last_typing_action[user_id] = current_time

        # Simulate typing action
        self.logger.debug(f"Sending chat action Typing to user {user_id}")
        # Create a task to simulate typing and return immediately to avoid blocking
        asyncio.create_task(self.simulate_action(user_id, seconds))

    async def simulate_action(self, user_id: int, seconds: int = 4, action: str = "typing"):
        """
        Simulates an action for a specific user.
        """
        async with self.client.action(user_id, action, delay=seconds):
            await asyncio.sleep(seconds)