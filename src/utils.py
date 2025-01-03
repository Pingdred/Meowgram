import asyncio
import functools
import os
import io
import ffmpeg
import base64
import logging
from PIL import Image
from enum import Enum

from telethon.events import NewMessage, CallbackQuery

# Conversational Form State
class CatFormState(Enum):
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    WAIT_CONFIRM = "wait_confirm"
    CLOSED = "closed"


def audio_to_voice(input_path: str) -> str:
    """Convert audio to Telegram voice format"""
    output_path = os.path.splitext(input_path)[0] + "_voice.ogg"
    ffmpeg.input(input_path).output(
        output_path,
        codec="libopus",
        audio_bitrate="32k",
        vbr="on",
        compression_level=10,
        frame_duration=60,
        application="voip"
    ).run()
    return output_path


def encode_image(image_bytes: bytes) -> str:
    """
    Encodes an image from bytes to a base64 string with a data URI scheme.
    Args:
        image_bytes (bytes): The image data in bytes.
    Returns:
        str: The base64 encoded image string with a data URI scheme.
    """
      
    image = Image.open(io.BytesIO(image_bytes))
    mime_type = image.format.lower()
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    return f"data:image/{mime_type};base64,{encoded_image}"


def encode_voice(voice_bytes: bytes) -> str:
    """
    Encodes a voice message from bytes to a base64 string with a data URI scheme.
    Args:
        voice_bytes (bytes): The voice data in bytes.
    Returns:
        str: The base64 encoded voice string with a data URI scheme.
    """
    encoded_voice = base64.b64encode(voice_bytes).decode("utf-8")
    mime_type = "audio/ogg" # Telegram voice messages are in OGG format

    return f"data:{mime_type};base64,{encoded_voice}"


def build_update(event: NewMessage.Event | CallbackQuery.Event) -> dict:
    update = {
        "message": {}
    }

    if isinstance(event, NewMessage.Event):
        update["message"]["message_id"] = event.message.id
    elif isinstance(event, CallbackQuery.Event):
        update["message"]["message_id"] = event.query.msg_id

    if event.sender:
        update["message"]["from"] = {
            "id": event.sender_id,
            "username": event.sender.username,
            "first_name": event.sender.first_name,
            "last_name": event.sender.last_name,
        }

    return update


async def clear_chat_history(meowgram, event: NewMessage.Event) -> bool:
    logger = logging.getLogger("meowgram")

    user_id = event.sender_id
    message_id = event.message.id

    cat_client = await meowgram.ensure_cat_connection(user_id)
    if not cat_client:
        logger.error(f"Could not clear Chehsire Cat conversation history for user {user_id}")
        return False
    
    
    wipe_conversation = cat_client.api.memory.wipe_conversation_history
    await asyncio.to_thread(
        functools.partial(wipe_conversation, _headers={"user_id": user_id})
    )

    start = message_id
    batch_size = 100

    while True:
        message_ids = list(range(start, start - batch_size, -1))
        try:
            await event.client.delete_messages(user_id, message_ids)
            start -= batch_size
        except Exception:
            #logger.error(f"Error deleting messages: {type(e)} - {e}")
            break
