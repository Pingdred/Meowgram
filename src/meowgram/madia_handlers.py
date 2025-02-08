import os
import shutil
import asyncio
import mimetypes

from tempfile import mkdtemp
from typing import Any, Dict, Optional

from telethon.tl.types import Message
from telethon.events import NewMessage

from cheshire_cat.client import CheshireCatClient
from utils import build_base_cat_message, encode_image, encode_voice


async def handle_unsupported_media(event: NewMessage.Event) -> Optional[Dict[str, Any]]:
    """
    Handle unsupported media types. This includes GIFs, video notes, polls, contacts, locations, and venues.

    Args:
        event: The Telegram event containing the message.

    Returns:
        A dictionary with the formatted message if an unsupported media type is found,
        or None otherwise.
    """
    message: Message = event.message
    base_msg = build_base_cat_message(event)

    unsupported_texts = {
        "gif": "*[GIF]* (Not supported)",
        "video": "*[Video]* (Not supported)", # It also handles video_notes, since it is a subclass of video.
        "poll": "*[Poll]* (Not supported)",
        "contact": "*[Contact]* (Not supported)",
        "geo": "*[Location]* (Not supported)", # It also handles venues, since it is a subclass of geo.
    }

    # Check for unsupported message types
    for attr, text in unsupported_texts.items():
        if getattr(message, attr, None):
            base_msg["text"] = text
            return base_msg

    # Handle special unsupported sticker types
    if message.sticker:
        mime = message.sticker.mime_type
        sticker_map = {
            "video/webm": "*[Video Sticker]* (Not supported)",
            "application/x-tgsticker": "*[Animated Sticker]* (Not supported)",
        }
        if mime in sticker_map:
            base_msg["text"] = sticker_map[mime]
            return base_msg

    return None  # No unsupported media found


async def handle_chat_media(event: NewMessage.Event) -> Optional[Dict[str, Any]]:
    """
    Handle media that can be included in the chat with the Cheshire Cat.

    Args:
        event: The Telegram event containing the message.

    Returns:
        A dictionary with the formatted message if a supported specific media is present,
        or None otherwise.
    """
    message: Message = event.message
    
    # If the media cannot be sent as a chat message skip it
    if not any((message.photo, message.sticker, message.voice)):
        return None

    base_msg = build_base_cat_message(event)

    media_bytes = await message.download_media(file=bytes)
    if media_bytes is None:
        base_msg["text"] = "*[Error downloading, suggest user resubmit file]*"
        return base_msg

    if message.photo:
        base_msg["image"] = await asyncio.to_thread(encode_image, media_bytes)
        base_msg["text"] = "*[Image]*"
        return base_msg

    # Check if the sticker is an image, 
    # even if the check for unsupported media types already passed. 
    if message.sticker and message.sticker.mime_type == "image/webp": 
        # The file attribute offer an easy way to access the attributes of a sticker
        emoji = message.file.emoji
        base_msg["image"] = await asyncio.to_thread(encode_image, media_bytes)
        base_msg["text"] = f"*[Telegram Sticker with associated emoji: {emoji}]*" if emoji else "*[Telegram Sticker]*"
        return base_msg

    if message.voice:
        base_msg["audio"] = await asyncio.to_thread(encode_voice, media_bytes)
        base_msg["text"] = "*[Voice Note]*"
        return base_msg


async def handle_file(event: NewMessage.Event, cat_client: CheshireCatClient):
    """
    Handle generic file uploads to the Cheshire Cat.

    Args:
        event: The Telegram event containing the document.
        cat_client: The client used to interact with the target service.
    """
    pass
    message: Message = event.message
    doc_mime = message.document.mime_type

    # Get the allowed mime types from the Cheshire Cat
    allowed_mime_types = (await asyncio.to_thread(cat_client.api.rabbit_hole.get_allowed_mimetypes))["allowed"]
    # Check if the file type is allowed
    if doc_mime not in allowed_mime_types:
        # Get the extensions from the allowed mime types
        exts_from_mimes = [mimetypes.guess_extension(mime, strict=False) or mime for mime in allowed_mime_types]
        # Remove the starting dot from the extensions
        exts_from_mimes = [ext[1:] if ext.startswith(".") else ext for ext in exts_from_mimes]

        await message.reply(
            f"Unsupported file type, only the following types are allowed: {', '.join(exts_from_mimes)}"
        )
        return
    
    media_bytes = await message.download_media(file=bytes)
    if media_bytes is None:
        await message.reply( 
            "A problem occurred while downloading the file from Telegram. Please try again."
        )
        return

    # The file attribute offer an easy way to acces the attributes of a document
    file_name = message.file.name

    def write_file(file_path: str, media_bytes: bytes):
        with open(file_path, 'wb') as f:
            f.write(media_bytes)
            # Ensure the file is written to disk
            f.flush()

    # Create a temporary directory
    temp_dir = mkdtemp()
    try:
        # Create the full path for the file
        file_path = os.path.join(temp_dir, file_name)

        # Write the file to disk in a separate thread
        # to avoid blocking the event loop for big files
        await asyncio.to_thread(write_file, file_path, media_bytes)
        
        # Upload the file to the Cheshire Cat
        await asyncio.to_thread(cat_client.api.rabbit_hole.upload_file, file_path)
    
    finally:
        # Remove the entire temporary directory and its contents
        shutil.rmtree(temp_dir, ignore_errors=True)

