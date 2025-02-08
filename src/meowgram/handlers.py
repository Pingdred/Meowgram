import re
import logging

from telethon.events import NewMessage, CallbackQuery, StopPropagation
from telethon.tl.custom import Message

from cheshire_cat.client import CheshireCatClient
from meowgram.madia_handlers import handle_unsupported_media, handle_chat_media, handle_file
from utils import clear_chat_history, build_base_cat_message


async def command_handler(mewogram, event: CallbackQuery.Event):
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


async def message_handler(meowgram, event: NewMessage.Event):
    """
    Main handler for incoming Telegram messages.

    Args:
        meowgram: The main bot instance with necessary methods.
        event: The incoming Telegram event containing the message.

    Note:
        This is the hierarchy of the message media types:

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
            ├── contact                             Shared contact information
            ├── geo                                 Geographic coordinates (latitude and longitude)
            │   └── venue                           Location with title and address
            ├── poll                                Interactive poll
            ├── web_preview                         Webpage preview (link preview)
            ├── game                                Telegram game (interactive game)
            ├── invoice                             Payment invoice (Telegram Payments)
            └── dice                                Animated emoji/dice (used for sending dynamic emojis or dice)
    """

    user_id = event.sender_id
    cat_client: CheshireCatClient = await meowgram.ensure_cat_connection(user_id)
    if not cat_client:
        return

    message: Message = event.message

    # If no media is present, send the text message directly.
    if not message.media:
        base_msg = build_base_cat_message(event)
        base_msg["text"] = message.text
        await cat_client.send_message(base_msg)
        return

    # Define the handlers for different media types in order of priority.
    handlers = [
        handle_unsupported_media,
        handle_chat_media,
    ]

    # Iterate through the handlers and return the first non-None result.
    for handler in handlers:
        result = await handler(event)

        # Skip to the next handler if the result is None.
        if result is None:
            continue
        
        # Add the caption associated with the media if present.
        if message.text:
            result["text"] = message.text
        await cat_client.send_message(result)

        # Stop processing the message after sending the media
        return

    # Send every other media down the Rabbit Hole
    if message.document:
        # if message.text:
        #     await message.reply("I'm reading the document, please wait a moment.")

        await handle_file(event, cat_client)


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

    message = build_base_cat_message(event)
    message["text"] = action

    form_action = {
        "form_name": form_name,
        "action": action #{}, # No information are needed for form actions
    }
    message["form_action"] = form_action

    await cat_client.send_message(message)

    await event.edit(buttons=None)
