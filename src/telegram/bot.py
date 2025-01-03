import re
import os
import time
import logging
import asyncio
import tempfile
import requests
from typing import Dict

from telethon import TelegramClient,  events, Button
from telethon.tl.types import BotCommand, BotCommandScopeDefault
from telethon.tl.functions.bots import SetBotCommandsRequest
from cheshire_cat.client import CheshireCatClient

from telegram.handlers import command_handler, message_handler, form_action_handler
from utils import audio_to_voice, CatFormState

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
        
        self.logger = logging.getLogger()

    def set_telegram_handlers(self):
        """Setup event handlers"""

        # Handler for commands
        self.client.add_event_handler(
            lambda event: command_handler(self, event), 
            events.NewMessage(pattern=r"/.*")
        )

        # Handler for messages
        self.client.add_event_handler(
            lambda event: message_handler(self, event),
            events.NewMessage
        )

        # Handler for form actions
        self.client.add_event_handler(
            lambda event: form_action_handler(self, event),
            events.CallbackQuery(pattern=r"form_.*"),
        )

    async def set_commands(self):
        # Delete all commands
        await self.client(SetBotCommandsRequest(scope=BotCommandScopeDefault(), lang_code='', commands=[]))

        # Set new commands
        commands = [
            BotCommand(command="clear", description="Clear chat history"),
        ]
        await self.client(SetBotCommandsRequest(scope=BotCommandScopeDefault() ,lang_code='', commands=commands))


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
            

    async def ensure_cat_connection(self, user_id: int) -> CheshireCatClient | None:
        """
        Ensures there is an active connection to Cheshire Cat for the user.
        If not, creates a new one.
        """
        
        # Create a new connection if one does not exist
        if user_id not in self.cat_connections:
            cat_client = CheshireCatClient(self.cat_url, self.cat_port, user_id)
            # Register the callback to handle responses
            cat_client.set_message_handler(
                lambda msg: self.dispatch_cat_message(user_id, msg)
            )

            # Store the connection in the dictionary
            self.cat_connections[user_id] = cat_client   
        else:
            # Get the existing connection
            cat_client = self.cat_connections[user_id] 
            
        # Open a new connection if the WebSocket is closed
        if cat_client.ws is None or cat_client.ws.closed:
            # Connect the client to Cheshire Cat
            connected = await cat_client.connect(str(user_id))

            if not connected:
                self.logger.error(f"Failed to connect to Cheshire Cat for user {user_id}")
                self.client.send_message(user_id, "Failed to connect to Cheshire Cat. Please try again later.")
                return None
            
            # Start the listening loop for messages
            asyncio.create_task(cat_client.listen())
                
        return self.cat_connections[user_id]

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
                self.client.send_message(user_id, f"An error occurred while processing your request: {message}")
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
        text = self.clean_code_blocks(message["text"])

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

    @staticmethod
    def clean_code_blocks(text):
        """
        Removes language specification from markdown code blocks for Telegram.
        Converts ```python\n to ```\n to prevent Telegram from showing the language twice.
        
        Args:
            text (str): The markdown text containing code blocks
            
        Returns:
            str: Cleaned text with language specifications removed
        """        
        # Pattern più preciso che:
        # - inizia con tre backtick (```)
        # - seguito da una o più lettere/numeri/underscore per il nome del linguaggio
        # - seguito da una nuova riga (\n)
        pattern = r'```([a-zA-Z0-9_]+)\n'
        
        return re.sub(pattern, '```\n', text)