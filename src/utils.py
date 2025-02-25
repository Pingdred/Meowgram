
import os
import io
import re
import ffmpeg
import base64
import logging
import asyncio

from typing import Optional

from PIL import Image
from enum import Enum
from pydantic import BaseModel


# Conversational Form State
class CatFormState(Enum):
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    WAIT_CONFIRM = "wait_confirm"
    CLOSED = "closed"


class PayloadType(Enum):
    FORM_ACTION = "form_action"
    NEW_MESSAGE = "new_message"
    USER_ACTION = "user_action" 


class UserInfo(BaseModel):
    id: int
    username: str
    first_name: str | None 
    last_name: str | None


class ReplyTo(BaseModel):
    is_from_bot: bool = False
    when: float
    text: Optional[str] = None
    audio: Optional[str] = None
    image: Optional[str] = None 


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


def clean_code_blocks(text):
    """
    Removes language specification from markdown code blocks for Telegram.
    Converts ```python\n to ```\n to prevent Telegram from showing the language twice.
    
    Args:
        text (str): The markdown text containing code blocks
        
    Returns:
        str: Cleaned text with language specifications removed
    """        

    pattern = r'```([a-zA-Z0-9_]+)\n'
    
    return re.sub(pattern, '```\n', text)


async def delete_ccat_conversation(meowgram, user_id: int) -> bool:
    logger = logging.getLogger("meowgram")

    cat_client = await meowgram.ensure_cat_connection(user_id)
    if not cat_client:
        logger.error(f"Could not delete Chehsire Cat conversation for user {user_id}")
        meowgram.client.send_message(user_id, "Could not connect to Chehsire Cat")
        return False

    wipe_conversation = cat_client.api.memory.wipe_conversation_history
    await asyncio.to_thread(wipe_conversation, _headers={"user_id": user_id})
    await meowgram.send_temporary_message(user_id, "Conversation history wiped")

    return True