import os
import shutil
import asyncio
import mimetypes

from tempfile import mkdtemp
from typing import Any, Dict, Optional, Tuple

from telethon import TelegramClient
from telethon.tl.types import Message, User
from telethon.events import NewMessage, CallbackQuery
from pydantic import BaseModel

from cheshire_cat.client import CheshireCatClient
from utils import encode_image, encode_voice, UserInfo, ReplyTo

"""
Hierarchy of the message media types:

Message
├── text                                    Text content of the message (can contain only text or a caption)
└── media                                   Media content attached to the message (if present)
    ├── photo                               Image sent as a photo
    ├── document                            Generic file content with extended attributes (can include various file types)
    │   ├── video                           Video content with thumbnail and duration
    │   │   └── video_note                  Round video message (usually 640x640)
    │   ├── audio                           Audio file with metadata (title, performer)
    │   │   └── voice                       Voice message recording
    │   ├── sticker                         Image or animation sticker
    │   │   ├── image/webp                  Image sticker (WebP format)
    │   │   ├── video/webm                  Video sticker (WebM format)
    │   │   └── application/x-tgsticker     Animated sticker (TGSticker format)
    │   ├── gif                             Animated image (GIF)
    │   │── file                            Generic file pdf, txt, etc.
    ├── contact                             Shared contact information
    ├── geo                                 Geographic coordinates (latitude and longitude)
    │   └── venue                           Location with title and address
    ├── poll                                Interactive poll
    ├── web_preview                         Webpage preview (link preview)
    ├── game                                Telegram game (interactive game)
    ├── invoice                             Payment invoice (Telegram Payments)
    └── dice                                Animated emoji/dice (used for sending dynamic emojis or dice)
"""



class NewMessageData(BaseModel):
    message_id: int
    user_info: UserInfo
    reply_to_message: Optional[ReplyTo] = None

    @classmethod
    async def from_event(cls, event: NewMessage.Event | CallbackQuery.Event) -> "NewMessageData":
        """
        Create a new instance of NewMessageData from a Telegram event.

        Args:
            event (NewMessage.Event | CallbackQuery.Event): The Telegram event containing the message.

        Returns:
            NewMessageData: The new instance of NewMessageData.
        """
        sender, message = await cls._get_sender_and_message(event)

        new_message_data = cls(
            message_id=message.id,
            user_info=UserInfo(
                id=sender.id,
                username=sender.username,
                first_name=sender.first_name,
                last_name=sender.last_name
            )
        )

        if message.reply_to:
            new_message_data.reply_to_message = await cls._handle_reply_to(message, event.client)

        return new_message_data
    
    @staticmethod
    async def _get_sender_and_message(event: NewMessage.Event | CallbackQuery.Event) -> Tuple[User, Message]:
        if isinstance(event, NewMessage.Event):
            return event.sender, event.message
        elif isinstance(event, CallbackQuery.Event):
            return event.query.sender, event.query.message

    @classmethod
    async def _handle_reply_to(cls, message: Message, client: TelegramClient) -> ReplyTo:
        """
        Handle the reply_to attribute of a Telegram message.
        """
        original_message = await cls._get_original_message(message, client)

        base_reply_to = await cls._build_base_reply_to(original_message, client)
        reply_to_message = await cls._set_media_content(base_reply_to, original_message)

        # Reset the text to the original message text if it is not empty
        # _set_media_content might have set a text message
        if original_message.text:
            reply_to_message.text = original_message.text

        return reply_to_message

    @staticmethod
    async def _get_original_message(message: Message, client: TelegramClient) -> Message:
        """
        Get the original message that the user is replying to.

        Args:
            message (Message): The message containing the reply_to attribute.
            client (TelegramClient): The client used to interact with the Telegram API.

        Returns:
            Message: The original message that the user is replying to.        
        """
        reply_to_msg_id = message.reply_to.reply_to_msg_id
        return await client.get_messages(message.chat_id, ids=reply_to_msg_id)

    @staticmethod
    async def _build_base_reply_to(original_message: Message, client: TelegramClient) -> ReplyTo:
        """
        Build a base ReplyTo object from a Telegram message.

        Args:
            original_message (Message): The original message to reply to.
            client (TelegramClient): The client used to interact with the Telegram API.

        Returns:
            ReplyTo: The base reply_to_message object.
        """

        bot_id = (await client.get_me()).id
        sender_id = original_message.sender_id

        return ReplyTo(
            when=original_message.date.timestamp(),
            is_from_bot=(sender_id == bot_id)
        )

    @staticmethod
    async def _set_media_content(reply_to_message: ReplyTo, message: Message) -> ReplyTo:
        """
        Build a ReplyTo object from a Telegram message.
        
        Args:
            reply_to_message (ReplyTo): The reply_to_message object to set the media content on.
            message (Message): The Telegram message containing the media content.

        Returns:
            ReplyTo: The reply_to_message object with the media content set.
        """

        if not message.media:
            return reply_to_message
        
        if user_message := (await handle_unsupported_media(message) or await handle_chat_media(message)):
            reply_to_message.text = user_message.text
            reply_to_message.image = user_message.image
            reply_to_message.audio = user_message.audio

        return reply_to_message


class FormActionData(BaseModel):
    form_name: str
    action: str


class MeowgramPayload(BaseModel):
    data: FormActionData | NewMessageData

    @classmethod
    async def from_event(cls, event:  NewMessage.Event | CallbackQuery.Event) -> "MeowgramPayload":
        return cls(
            data=await NewMessageData.from_event(event)
        )
    

class UserMessage(BaseModel):
    text: Optional[str] = None
    image: Optional[str] = None
    audio: Optional[str] = None
    meowgram: Optional[MeowgramPayload] = None


async def handle_unsupported_media(event: NewMessage.Event | Message) -> Optional[UserMessage]:
    """
    Handle unsupported media types. This includes GIFs, video notes, polls, contacts, locations, and venues.

    Args:
        event: The Telegram event containing the message.

    Returns:
        A dictionary with the formatted message if an unsupported media type is found,
        or None otherwise.
    """

    if isinstance(event, NewMessage.Event):
        message: Message = event.message
    else:
        message: Message = event    

    user_massage = UserMessage()

    if isinstance(event, NewMessage.Event):
        user_massage.meowgram = await MeowgramPayload.from_event(event)

    unsupported_texts = {
        "gif": "*[GIF]* (Not supported)",
        "video": "*[Video]* (Not supported)", # It also handles video_notes, since it is a subclass of video.
        "poll": "*[Poll]* (Not supported)",
        "contact": "*[Contact]* (Not supported)",
        "geo": "*[Location]* (Not supported)", # It also handles venues, since it is a subclass of geo.
    }

    # Check for unsupported message types
    for attr, text in unsupported_texts.items():

        # Set the mapped text if thre is an unsupported media type
        if getattr(message, attr, None):
            user_massage.text = text
            return user_massage

    # Check manually for unsupported stickers types
    if message.sticker:
        mime = message.sticker.mime_type

        sticker_map = {
            "video/webm": "*[Video Sticker]* (Not supported)",
            "application/x-tgsticker": "*[Animated Sticker]* (Not supported)",
        }

        # Set the mapped text if there is an unsupported sticker type
        if mime in sticker_map:
            user_massage.text = sticker_map[mime]
            return user_massage

    return None  # No unsupported media found


async def handle_chat_media(event: NewMessage.Event | Message) -> Optional[Dict[str, Any]]:
    """
    Handle media that can be included in the chat with the Cheshire Cat.

    Args:
        event: The Telegram event containing the message.

    Returns:
        A dictionary with the formatted message if a supported specific media is present,
        or None otherwise.
    """
    
    if isinstance(event, NewMessage.Event):
        message: Message = event.message
    else:
        message: Message = event
    
    # If the media cannot be sent as a chat message skip this handler
    if not any((message.photo, message.sticker, message.voice)):
        return None
    
    user_message = UserMessage()

    if isinstance(event, NewMessage.Event):
        user_message.meowgram = await MeowgramPayload.from_event(event)

    media_bytes = await message.download_media(file=bytes)

    # In case of an error while downloading the file,
    # inform the user and return
    if media_bytes is None:
        user_message.text = "*[Error downloading, suggest user resubmit file]*"
        return user_message

    if message.photo:
        user_message.image = await asyncio.to_thread(encode_image, media_bytes)
        user_message.text = "*[Image]*"
        return user_message

    # Check for video or animated stickers was already done in handle_unsupported_media
    # but to be sure we check again here if the sticker is an image
    if message.sticker and message.sticker.mime_type == "image/webp": 
        # The file attribute offer an easy way to access the attributes of a sticker
        emoji = message.file.emoji
        user_message.image = await asyncio.to_thread(encode_image, media_bytes)
        user_message.text = f"*[Telegram Sticker with associated emoji: {emoji}]*" if emoji else "*[Telegram Sticker]*"
        return user_message

    if message.voice:
        user_message.audio = await asyncio.to_thread(encode_voice, media_bytes)
        user_message.text = "*[Voice Note]*"
        return user_message


async def handle_file(event: NewMessage.Event, cat_client: CheshireCatClient) -> None:
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

    # In case of an unsupported file type, 
    # inform the user and return
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

    # In case of an error while downloading the file, 
    # inform the user and return
    if media_bytes is None:
        await message.reply( 
            "A problem occurred while downloading the file from Telegram. Please try again."
        )
        return

    # The file attribute offer an easy way to acces the attributes of a document
    file_name = message.file.name

    def write_file(file_path: str, media_bytes: bytes):
        """
            Utility function to write the media bytes to a file on disk.
            Needed to run it in a separate thread using asyncio.to_thread.
        """
        with open(file_path, 'wb') as f:
            f.write(media_bytes)
            # Ensure the file is written to disk
            f.flush()

    temp_dir = mkdtemp()
    try:
        # Get the full path where the file will be temporarily stored
        file_path = os.path.join(temp_dir, file_name)

        # Write the file to disk in a separate thread
        # to avoid blocking the event loop for big files
        await asyncio.to_thread(write_file, file_path, media_bytes)
        
        # Upload the file to the Cheshire Cat
        await asyncio.to_thread(cat_client.api.rabbit_hole.upload_file, file_path, _headers={"user_id": event.sender_id})
    
    finally:
        # Remove the entire temporary directory and its contents
        # ingore_errors=True prevents the function to block the
        # event loop in case of errors, so there is no need to run
        # it in a separate thread
        shutil.rmtree(temp_dir, ignore_errors=True)

