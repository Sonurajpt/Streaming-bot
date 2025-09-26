# bot.py
# Requirements: python-telegram-bot==13.15, requests, beautifulsoup4
# This script uses long-polling. Make sure TELEGRAM_TOKEN is set as an env var.

import os
import re
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- config ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PROXY_BASE = os.environ.get("PROXY_BASE", "")  # Example: https://streaming-bot-1.onrender.com/proxy?url=
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# --- logging ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("terabox-bot")

# --- token check ---
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN is not set in environment. Exiting.")
    raise SystemExit("TELEGRAM_TOKEN is not configured")


# --- helper: extract share id ---
def extract_possible_share_id(url: str):
    if not url:
        return None
    match = re.search(r"/s/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else None


# --- helper: find direct video link ---
def find_direct_video(url: str):
    try:
        headers = {"User-Agent": USER_AGENT}
        target_url = url

        # Agar proxy diya gaya hai to proxy ke through request kare
        if PROXY_BASE:
    # ensure proxy base always ends with ?url=
    if not PROXY_BASE.endswith("?url="):
        proxy_base = PROXY_BASE.rstrip("/") + "/proxy?url="
    else:
        proxy_base = PROXY_BASE
    target_url = f"{proxy_base}{url}"
else:
    target_url = url

        resp = requests.get(target_url, headers=headers, timeout=10)
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        video_tag = soup.find("video")
        if video_tag and video_tag.get("src"):
            return video_tag["src"]

        # fallback regex
        match = re.search(r'https?://[^"\']+\.mp4', html)
        if match:
            return match.group(0)

        return None
    except Exception as e:
        logger.error(f"Error in find_direct_video: {e}")
        return None


# --- commands ---
def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Hi! Send me a Terabox link and I'll try to fetch a direct video link.")


def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if not text.startswith("http"):
        update.message.reply_text("❌ Please send a valid Terabox link.")
        return

    update.message.reply_text("⏳ Processing your link... Please wait.")

    video_url = find_direct_video(text)
    if video_url:
        update.message.reply_text(f"✅ Direct video link found:\n{video_url}")
    else:
        update.message.reply_text("❌ Sorry, I couldn't extract a direct video link.")


# --- main ---
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    logger.info("Bot started...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
