import base64
import os
import re
import time
import logging
import asyncio
import tempfile
import requests

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Set

from telethon import TelegramClient, Button
from telethon.events import NewMessage, CallbackQuery, StopPropagation
from telethon.errors import MessageIdInvalidError
from telethon.tl.types import Message, User
from cheshire_cat.client import CheshireCatClient

from meowgram.menu.menu import MenuManager, MenuButton
from meowgram.madia_handlers import (
    handle_unsupported_media,
    handle_chat_media,
    handle_file,
    UserMessage,
    MeowgramPayload,
    FormActionData
)
from utils import (
    audio_to_voice,
    CatFormState,
    clean_code_blocks,
    delete_ccat_conversation
)


class AccessType(Enum):
    ALL = "all"
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"
    #CCAT_AUTH = 3


@dataclass
class AccessControl:
    access_type: AccessType
    users: Set[int]

    def __post_init__(self):
        try:
            ac_type = AccessType(self.access_type)
            self.access_type = ac_type
        except ValueError:
            self.access_type = AccessType.ALL
            logging.error(f"Invalid access type: {self.access_type}, defaulting to {AccessType.ALL}")

    def is_user_allowed(self, sender: User) -> bool:

        if sender.bot:
            logging.warning(f"{sender.id} is a bot. Refusing access.")  
            return False

        user_id = sender.id

        logging.debug(f"Checking user {user_id} against {self.access_type}")
        logging.debug(f"Users: {self.users}")

        if self.access_type == AccessType.ALL:
            logging.debug("All users are allowed.")
            return True

        if self.access_type == AccessType.WHITELIST:
            allowed = user_id in self.users
            if not allowed:
                logging.warning("User is not whitelisted. Refusing access.")
            return allowed

        if self.access_type == AccessType.BLACKLIST:
            allowed = user_id not in self.users
            if not allowed:
                logging.warning(f"User {user_id} is blacklisted. Refusing access.")
            return allowed
        
        logging.warning(f"Unknown access type: {self.access_type}. Refusing access.")
        return False


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

        self.access_control = AccessControl(
            access_type=os.getenv("ACCESS_TYPE", "all"),
            users=[int(id) for id in os.getenv("ACCESS_LIST", "").split(",")],
        )
        self.menu_handler = MenuManager()

        self.logger = logging.getLogger(__name__)

    # SECTION: Telegram event handler
    
    def require_allowed_user(func):
        """Decorator to check if the user is allowed to use the bot"""
        async def wrapper(self, event, *args, **kwargs):
            if not self.access_control.is_user_allowed(event._sender):
                await event.reply("You are not allowed to use this bot.")
                raise StopPropagation
            return await func(self, event, *args, **kwargs)
        return wrapper

    @require_allowed_user
    async def menu_handler(self, event: NewMessage.Event):
        current_menu = self.menu_handler.get_current_menu(event.sender_id)

        handled = False
        try:
            handled = await self.menu_handler.handle_menu(event)
        except (Exception, BaseException) as e:
            from traceback import print_exc
            print_exc()
            logging.error(f"An error occurred handling the menu `{current_menu}`: {str(e)}")
            handled = True

        if handled:
            raise StopPropagation

    @require_allowed_user
    async def command_handler(self, event: CallbackQuery.Event):
        """Handle commands"""
        command = event.message.text
        try:
            match command:
                case "/start":
                    menu = self.menu_handler.get_keyboard("main")
                    await event.reply("Welcome to Meowgram! How can I help you today?", buttons=menu)
                    self.menu_handler.set_current_menu(event.sender_id, "main")
        except Exception as e:
            from traceback import print_exc
            self.logger.error(f"An error occurred handling the command {command}: {e}")
            print_exc()
        finally:
            raise StopPropagation

    @require_allowed_user
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

        # Remove buttons from the previous message if present
        previus_message_id = event.message.id - 1
        previus_message: Message = await self.client.get_messages(user_id, ids=previus_message_id)
        try:
            if (previus_message is not None) and (previus_message.buttons is not None):
                await self.client.edit_message(entity=previus_message, buttons=None)
        except MessageIdInvalidError:
            logging.debug(f"Message {previus_message_id} not found or unable to edit")

        if not cat_client:
            logging.error("Could not connect to Cheshire Cat")
            raise StopPropagation

        message: Message = event.message

        # If no media is present, send the text message directly.
        if not message.media:
            new_message = UserMessage(
                text=message.text,
                meowgram= await MeowgramPayload.from_event(event)
            )

            await cat_client.send_message(new_message)
            return

        # If the media is an unsupported media type, or a suppoted chat media, handle it
        if user_message := await handle_unsupported_media(event) or await handle_chat_media(event):
            # Add the caption associated with the media if present.
            if message.text:
               user_message.text = message.text

            await cat_client.send_message(user_message)
            return

        # Send every other media down the Rabbit Hole
        # document is checked last as it's the most generic media type
        if message.document:
            # TODO: Handle caption for document
            await handle_file(event, cat_client)

    @require_allowed_user
    async def form_action_handler(self, event: CallbackQuery.Event):
        """Handle form actions"""
        user_id = event.sender_id

        cat_client = await self.ensure_cat_connection(user_id)
        if not cat_client:
            logging.error("Could not connect to Cheshire Cat")
            raise StopPropagation

        query = event.data.decode("utf-8")

        pattern = r"^form_(?P<form_name>[a-zA-Z0-9_]+)_(?P<action>confirm|cancel)$"
        match = re.match(pattern, query)

        if not match:
            return
        

        form_action_data = FormActionData(
            form_name=match.group("form_name"),
            action=match.group("action")
        )

        user_message = UserMessage(
            meowgram=MeowgramPayload(
                data=form_action_data
            )
        )

        await cat_client.send_message(user_message)
        await event.edit(buttons=None)


    # SECTION: Bot initialization

    def setup_menus(self):
        main_menu = [
            [MenuButton(text="🧹 Clear chat history", submenu="chat_history_menu")]
        ]

        chat_history_menu = [
            [MenuButton(
                text="Yes, clear chat history",
                callback=lambda e: delete_ccat_conversation(self, e.sender_id),
                submenu="main"
            )],
            [MenuButton(text="No, cancel", submenu="main")],
        ]

        self.menu_handler.create_menu("main", main_menu, parent="main")
        self.menu_handler.create_menu("chat_history_menu", chat_history_menu, parent="main")

    def set_telegram_handlers(self):
        """Setup event handlers"""

        # Handler for menus
        self.client.add_event_handler(
            self.menu_handler,
            NewMessage(incoming=True)
        )

        # Handler for commands
        self.client.add_event_handler(
            self.command_handler, 
            NewMessage(pattern=r"/.*", incoming=True)
        )

        # Handler for messages
        self.client.add_event_handler(
            self.message_handler,
            NewMessage(incoming=True)
        )

        # Handler for form actions
        self.client.add_event_handler(
            self.form_action_handler,
            CallbackQuery(pattern=r"form_.*"),
        )

    # SECTION: Bot lifecycle

    async def run(self):
        """Start bot with unified message handler"""        
        try:
            # Create the bot menus
            self.setup_menus()

            # Start the bot
            await self.client.start(bot_token=self.bot_token)

            self.logger.info("Bot started and listening")

            # Run the bot until it is disconnected
            await self.client.disconnected
        except asyncio.CancelledError:
            self.logger.info("Safely shutting down bot")
        except Exception as e:
            from traceback import print_exc
            self.logger.error(f"An error occurred while running the bot: {e}")
            print_exc()
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
                self.logger.error("Failed to connect to Cheshire Cat")
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
                self.logger.info(f"Notification message received from Cheshire Cat: {message}")
                await self.send_temporary_message(user_id, message["content"])
            case _:
                self.logger.error(f"Unknown message type received from Cheshire Cat: {message}")           

    async def handle_chat_message(self, user_id: int, message: dict):
        # Extract Meowgram-specific parameters if present
        meowgram_params = message.get("meowgram", {})
        send_params = meowgram_params.get("send_params", {})
        settings = meowgram_params.get("settings", {"show_tts_text": False})
        
        # Handle form buttons
        buttons = None
        active_form = meowgram_params.get("active_form")
        if active_form:
            form_state = active_form["state"]
            form_name = active_form["name"].replace(" ", "_").lower()
            button_list = []
            
            if form_state == CatFormState.WAIT_CONFIRM.value:
                button_list.append([
                    Button.inline("Confirm", 
                        data=f"form_{form_name}_confirm")
                ])
            
            if form_state != CatFormState.CLOSED.value:
                button_list.append([
                    Button.inline("Cancel",
                        data=f"form_{form_name}_cancel")
                ])
            
            buttons = button_list if button_list else None

        if len(message["text"]) > 4000:
            # Send as a file if the message is too long
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as file:
                file.write(message["text"])
                file_path = file.name

            await self.client.send_file(
                user_id,
                file_path,
                buttons=buttons,
                **send_params
            )
            os.remove(file_path)
            message["text"] = None

        # Handle TTS
        if  message.get("audio"):
            voice_path = await self.process_audio(message)
            caption = message["text"] if settings["show_tts_text"] else None
            await self.client.send_file(
                user_id,
                voice_path,
                voice_note=True,
                caption=caption,
                buttons=buttons,
                **send_params
            )
            await asyncio.to_thread(os.remove, voice_path)
            return
                
        if not message.get("text"):
            return
        
        # Remove language specification from code blocks
        # to prevent Telegram from showing the language twice
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
            self.logger.debug("Skipping chat action Typing to user ")
            return

        # Update the time of the last typing action
        self.last_typing_action[user_id] = current_time

        # Simulate typing action
        self.logger.debug(f"Sending chat action Typing to user ")
        # Create a task to simulate typing and return immediately to avoid blocking
        asyncio.create_task(self.simulate_action(user_id, seconds))

    async def simulate_action(self, user_id: int, seconds: int = 4, action: str = "typing"):
        """
        Simulates an action for a specific user.
        """
        async with self.client.action(user_id, action, delay=seconds):
            await asyncio.sleep(seconds)
           
    async def process_audio(self, message: dict):
        """
        Handles an audio message from Cheshire Cat.

        Args:
            user_id (int): The ID of the user to send the audio message to.
            message (dict): The audio message to be sent.
        """
        audio = message.get("audio")
        # Check if audio is a data uri
        if audio.startswith("data:"):
            # Extract the mime type and the base64 encoded audio
            encoded_audio = audio.split(";base64,")[1]
            audio_data = base64.b64decode(encoded_audio)
            ext = audio.split(";")[0].split("/")
            ext = '.' +  ext[1] if len(ext) > 1 else '.' + "ogg"

            # Save the audio to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(audio_data)
                tmp.seek(0)
                return tmp.name
    
        # Otherwise should be an URL
        response = requests.get(audio)
        if response.status_code == 200:
            ext = '.' + response.headers.get('content-type').split('/')[-1]
            # Save the audio to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(response.content)
                tmp.seek(0)            
            return tmp.name
                tmp.write(response.content)
                tmp.seek(0)
                voice_path = await asyncio.to_thread(audio_to_voice, tmp.name)
            
            return voice_path

    async def send_temporary_message(self, user_id: int, message: str, seconds: int = 7):
        """
        Sends a message to a user after a specified delay.
        """
        
        async def background_task():
            msg = await self.client.send_message(user_id, message)
            await asyncio.sleep(seconds)
            await msg.delete()

        asyncio.create_task(background_task())
    