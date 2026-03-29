import asyncio
import logging
import os
import re
import yt_dlp
import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE_MB = 50

FFMPEG_PATH = r'C:\ffmpeg-8.1-essentials_build\ffmpeg-8.1-essentials_build\bin' if os.name == 'nt' else None


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = name.strip('. ')
    return name[:200] or "audio"


def download_song_as_mp3(song_name: str) -> tuple[str | None, str | None]:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': FFMPEG_PATH,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{song_name}", download=True)

        if not info or 'entries' not in info or not info['entries']:
            return None, None

        video = info['entries'][0]
        title = video.get('title', 'audio')
        raw_path = ydl.prepare_filename(video)
        file_path = os.path.splitext(raw_path)[0] + '.mp3'

        return file_path, title


WELCOME_TEXT = (
    "🎵 *Music Bot*\n\n"
    "Send me the name of any song and I'll find it on YouTube and send you the MP3.\n\n"
    "*Examples:*\n"
    "• `Bohemian Rhapsody Queen`\n"
    "• `Eminem Lose Yourself`\n"
    "• `Blinding Lights The Weeknd`\n\n"
    "The file will be sent as an audio track you can play or save directly on your phone or computer."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    song_name = update.message.text.strip()
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text(f"Searching for *{song_name}*...", parse_mode="Markdown")
    file_path = None

    try:
        await status_msg.edit_text(f"Downloading *{song_name}*...", parse_mode="Markdown")
        file_path, title = download_song_as_mp3(song_name)

        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("Could not find or download that song. Try a different search.")
            return

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            await status_msg.edit_text(
                f"The file is too large ({file_size_mb:.1f} MB). Telegram allows max {MAX_FILE_SIZE_MB} MB."
            )
            return

        await status_msg.edit_text("Sending...")

        performer, track = None, title
        if title and ' - ' in title:
            parts = title.split(' - ', 1)
            performer, track = parts[0].strip(), parts[1].strip()

        with open(file_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                title=track,
                performer=performer,
                caption=f"🎵 {title}"
            )

        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling song '{song_name}': {e}")
        await status_msg.edit_text("An error occurred. Please try again.")

    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


async def run():
    if not TOKEN:
        raise ValueError("BOT_TOKEN not found in .env file.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async with app:
        await app.start()
        print("Bot is running. Send a song name in Telegram.")

        offset = None
        while True:
            try:
                updates = await app.bot.get_updates(
                    offset=offset,
                    timeout=10,
                    allowed_updates=["message"],
                    read_timeout=20,
                )
                for update in updates:
                    await app.process_update(update)
                    offset = update.update_id + 1

            except telegram.error.Conflict:
                logging.warning("Conflict: another instance is running. Waiting 30s before retrying...")
                await asyncio.sleep(30)

            except telegram.error.TimedOut:
                pass

            except telegram.error.NetworkError as e:
                logging.warning(f"Network error: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

            except Exception as e:
                logging.error(f"Unexpected error: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

        await app.stop()


if __name__ == '__main__':
    asyncio.run(run())
