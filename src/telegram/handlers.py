import re
import asyncio
import logging
from typing import Any, Dict

from telethon.tl.types import Message
from telethon.events import NewMessage, CallbackQuery, StopPropagation

from utils import clear_chat_history, build_update, encode_image, encode_voice

async def command_handler(mewogram, event):
    """Handle commands"""
    command = event.message.text
    logger = logging.getLogger()
    try:
        match command:
            case "/start":
                await event.reply("Welcome to Meowgram! How can I help you today?")

            case "/clear":
                await clear_chat_history(mewogram, event)
    except Exception as e:
       logger.error(f"An error occurred handling the command {command}: {e}")
    finally:
        raise StopPropagation


async def message_handler(meowgram , event: NewMessage.Event):
    """Handle messages"""
    user_id = event.sender_id

    cat_client = await meowgram.ensure_cat_connection(user_id)
    if not cat_client:
        return
    
    incoming_message = event.message
    new_message = {
        "meowgram": {
            "update": build_update(event)
        }
    }

    if incoming_message.media:
        await handle_media(event, new_message)

    if incoming_message.text:
        new_message["text"] = incoming_message.text

    # Send the message to Cheshire Cat
    await cat_client.send_message(new_message)


async def handle_media(event: NewMessage.Event, new_message: Dict[str, Any]) -> Dict[str, Any]:
    """Handle different types of media messages from Telegram.
    
    Args:
        event: Telegram event containing the message
        new_message: Dictionary to store processed message data
    
    Returns:
        Dictionary containing processed message data
    """
    message: Message = event.message

    message.photo


    print(message.to_dict())

    match message:
        # Image-like media
        case m if m.photo:
            media_bytes = await message.download_media(file=bytes)
            new_message["image"] = await asyncio.to_thread(encode_image, media_bytes)
            new_message["text"] = "*[Image]*"

        case m if m.sticker:
            match m.sticker.mime_type:
                case "image/webp":
                    # Get the emoji associated with the sticker
                    emoji = m.sticker.attributes[1].alt 
                    media_bytes = await message.download_media(file=bytes)
                    new_message["image"] = await asyncio.to_thread(encode_image, media_bytes)
                    new_message["text"] = f"*[Sticker]* {emoji}"
                case "application/x-tgsticker":
                    new_message["text"] = "*[Animated Sticker]* (Not supported)"
                case "video/webm":
                    new_message["text"] = "*[Video Sticker]* (Not supported)"

        # Audio media 
        # Video notes are treated as voice notes by Telegram, 
        # but they are video so we need to handle them separately
        case m if (m.voice or m.audio) and not m.video_note:
            new_message["text"] = "*[Voice Note]*"
            media_bytes = await message.download_media(file=bytes)
            new_message["audio"] = await asyncio.to_thread(encode_voice, media_bytes)

        # Unsupported media types
        case m if m.video or m.video_note:
            new_message["text"] = "*[Video]* (Not supported)"
        case m if m.gif:
            new_message["text"] = "*[GIF]* (Not supported)"
        case m if m.poll:
            new_message["text"] = "*[Poll]* (Not supported)"
        case m if m.contact:
            new_message["text"] = "*[Contact]* (Not supported)"
        case m if m.geo:
            new_message["text"] = "*[Location]* (Not supported)"
        case m if m.venue:
            new_message["text"] = "*[Venue]* (Not supported)"
        
    return new_message


async def form_action_handler(meowgram, event: CallbackQuery.Event):
    """Handle form actions"""
    user_id = event.sender_id

    cat_client = await meowgram.ensure_cat_connection(user_id)
    if not cat_client:
        return

    query = event.data.decode("utf-8")

    pattern = r"^form_(?P<form_name>[a-zA-Z0-9_]+)_(?P<action>confirm|cancel)$"
    match = re.match(pattern, query)

    if not match:
        return


    form_name = match.group('form_name')
    action = match.group("action")

    message = {
        "text": action,
        "meowgram": {
            "update": build_update(event), #{}, # No information are needed for form actions
            "form_action": {
                "form_name": form_name,
                "action": action
            }
        }
    }

    await cat_client.send_message(message)

    await event.edit(buttons=None)
