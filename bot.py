import logging
import os
import re
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Load token from .env file
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Temporary download folder
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Telegram bot max file size (50 MB)
MAX_FILE_SIZE_MB = 50


def sanitize_filename(name: str) -> str:
    """Remove all characters that are invalid in filenames."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = name.strip('. ')
    return name[:200] or "audio"  # Limit length, fallback if empty


def download_song_as_mp3(song_name: str) -> tuple[str | None, str | None]:
    """
    Search YouTube for the song, download best audio, convert to MP3.
    Returns (file_path, video_title) or (None, None) on failure.
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': r'C:\ffmpeg-8.1-essentials_build\ffmpeg-8.1-essentials_build\bin' if os.name == 'nt' else None,
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

        # Use yt-dlp's own filename logic to avoid sanitization mismatches
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
    """Handle text messages: treat them as song names, download and send MP3."""
    song_name = update.message.text.strip()
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text(f"🔍 Searching for *{song_name}*...", parse_mode="Markdown")
    file_path = None

    try:
        await status_msg.edit_text(f"⬇️ Downloading *{song_name}*...", parse_mode="Markdown")
        file_path, title = download_song_as_mp3(song_name)

        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Sorry, I couldn't find or download that song. Try a different search.")
            return

        # Check file size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            await status_msg.edit_text(
                f"❌ The file is too large ({file_size_mb:.1f} MB). Telegram allows a max of {MAX_FILE_SIZE_MB} MB."
            )
            return

        await status_msg.edit_text("📤 Sending...")

        # Extract artist/track from title if possible (e.g. "Artist - Song")
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
        await status_msg.edit_text("⚠️ An error occurred. Please try again later.")

    finally:
        # Always clean up the file
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


def main() -> None:
    if not TOKEN:
        raise ValueError("BOT_TOKEN not found. Make sure your .env file is set up correctly.")

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
