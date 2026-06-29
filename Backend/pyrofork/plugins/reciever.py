from asyncio import create_task, sleep as asleep, Queue, Lock
import Backend
from Backend.helper.task_manager import edit_message
from Backend.logger import LOGGER
from Backend import db
from Backend.config import Telegram
from Backend.helper.pyro import clean_filename, get_readable_file_size, remove_urls
from Backend.helper.metadata import metadata, extract_default_id
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums.parse_mode import ParseMode
from Backend.helper.encrypt import encode_string


file_queue = Queue()
db_lock = Lock()


async def process_file():
    while True:
        metadata_info, channel, msg_id, size, title = await file_queue.get()
        async with db_lock:
            updated_id = await db.insert_personal_file(
                metadata_info, channel=channel, msg_id=msg_id, size=size, name=title
            )
            if updated_id:
                LOGGER.info(f"Personal file saved: {title} (ID: {updated_id})")
            else:
                LOGGER.info(f"Failed to save: {title}")
        file_queue.task_done()


for _ in range(1):
    create_task(process_file())


def get_file_from_message(message: Message):
    """Return (file_obj, title) for any supported file type."""
    if message.video:
        f = message.video
        return f, message.caption or f.file_name or "video.mp4"
    if message.document:
        f = message.document
        return f, message.caption or f.file_name or "document"
    if message.audio:
        f = message.audio
        return f, message.caption or f.file_name or f.title or "audio"
    if message.photo:
        # photos have no file_name; use caption or generate one
        return message.photo, message.caption or "photo.jpg"
    return None, None


@Client.on_message(
    filters.channel & (
        filters.document | filters.video | filters.audio
    )
)
async def file_receive_handler(client: Client, message: Message):
    if str(message.chat.id) not in Telegram.AUTH_CHANNEL:
        await message.reply_text("> Channel is not in AUTH_CHANNEL")
        return

    try:
        file, raw_title = get_file_from_message(message)
        if not file:
            return

        msg_id = message.id
        size = get_readable_file_size(getattr(file, "file_size", 0))
        channel = str(message.chat.id).replace("-100", "")

        # Extract folder override from caption (e.g. "folder:Education")
        folder_override = None
        if message.caption:
            folder_override = extract_default_id(message.caption)

        title = clean_filename(raw_title or "file")
        metadata_info = await metadata(title, int(channel), msg_id, override_id=folder_override)
        if metadata_info is None:
            LOGGER.warning(f"Metadata failed for: {title}")
            return

        title = remove_urls(title)

        await file_queue.put((metadata_info, int(channel), msg_id, size, title))

    except FloodWait as e:
        LOGGER.info(f"Sleeping for {str(e.value)}s")
        await asleep(e.value)
    except Exception as e:
        LOGGER.error(f"file_receive_handler error: {e}")


@Client.on_edited_message(
    filters.channel & (filters.document | filters.video | filters.audio)
)
async def file_edited_handler(client: Client, message: Message):
    if str(message.chat.id) not in Telegram.AUTH_CHANNEL:
        return

    try:
        file, raw_title = get_file_from_message(message)
        if not file:
            return

        msg_id = message.id
        size = get_readable_file_size(getattr(file, "file_size", 0))
        channel = str(message.chat.id).replace("-100", "")

        folder_override = None
        if message.caption:
            folder_override = extract_default_id(message.caption)

        if folder_override:
            stream_id_hash = await encode_string({"chat_id": int(channel), "msg_id": msg_id})
            await db.delete_media_by_stream_id(stream_id_hash)

        title = clean_filename(raw_title or "file")
        metadata_info = await metadata(title, int(channel), msg_id, override_id=folder_override)
        if metadata_info is None:
            return

        title = remove_urls(title)
        await file_queue.put((metadata_info, int(channel), msg_id, size, title))

    except Exception as e:
        LOGGER.error(f"file_edited_handler error: {e}")


@Client.on_deleted_messages(filters.channel)
async def file_deleted_handler(client: Client, messages: list[Message]):
    try:
        for message in messages:
            if message.chat and str(message.chat.id) in Telegram.AUTH_CHANNEL:
                channel = str(message.chat.id).replace("-100", "")
                msg_id = message.id
                try:
                    stream_id_hash = await encode_string({"chat_id": int(channel), "msg_id": msg_id})
                    deleted = await db.delete_media_by_stream_id(stream_id_hash)
                    if deleted:
                        LOGGER.info(f"Purged deleted message {msg_id} from DB.")
                except Exception as ex:
                    LOGGER.error(f"Failed to scrub deleted message {msg_id}: {ex}")
    except Exception as e:
        LOGGER.error(f"file_deleted_handler error: {e}")
