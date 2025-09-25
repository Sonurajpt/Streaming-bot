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
PROXY_BASE = os.environ.get("PROXY_BASE", "")  # e.g. https://<your-app>.onrender.com/proxy?url=
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# --- logging ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("terabox-bot")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN is not set in environment. Exiting.")
    raise SystemExit("TELEGRAM_TOKEN not configured")

def extract_possible_share_id(url: str):
    """
    Simple heuristics to find TeraBox share id or return original url if nothing special.
    Adjust patterns if needed.
    """
    patterns = [
        r"(https?:\/\/(?:www\.)?terabox\.com\/[^\s]*)",
        r"(https?:\/\/(?:www\.)?terabox\.cn\/[^\s]*)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return url

def find_direct_video(url: str, timeout=15):
    """
    Try to extract direct .m3u8/.mp4 link from page HTML/scripts.
    Returns the first match or None.
    """
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    html = resp.text

    # quick search for obvious urls
    m = re.search(r"https?:\/\/[^\s'\"<>]+(?:\.m3u8|\.mp4)[^\s'\"<>]*", html)
    if m:
        return m.group(0)

    # parse scripts for JSON-like objects
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        txt = script.string
        if not txt:
            continue
        m = re.search(r"https?:\/\/[^\s'\"<>]+(?:\.m3u8|\.mp4)[^\s'\"<>]*", txt)
        if m:
            return m.group(0)

    return None

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Send me a TeraBox share link and I'll try to extract a streaming URL (only for files you have permission to access).")

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("Send a TeraBox share link (https://...). I'll look for mp4/m3u8 and return direct or proxied URL.")

def handle_message(update: Update, context: CallbackContext):
    txt = (update.message.text or "").strip()
    chat_id = update.message.chat_id
    logger.info("Received message from %s: %s", chat_id, txt[:200])

    if not txt:
        update.message.reply_text("Please send a valid URL.")
        return

    update.message.reply_text("Checking the link — dekh raha hoon...")

    # Sanitize / normalize
    target = extract_possible_share_id(txt)

    try:
        video = find_direct_video(target)
    except requests.RequestException as e:
        logger.warning("Request error while fetching %s: %s", target, e)
        update.message.reply_text(f"Error fetching the page: {e}")
        return
    except Exception as e:
        logger.exception("Unexpected error")
        update.message.reply_text(f"Unexpected error: {e}")
        return

    if video:
        # prepare proxied URL if PROXY_BASE set
        proxied = PROXY_BASE + requests.utils.requote_uri(video) if PROXY_BASE else None
        msg = f"✅ Direct video URL found:\n{video}"
        if proxied:
            msg += f"\n\n▶️ Proxied (use this if player has CORS issues):\n{proxied}"
        else:
            msg += "\n\n(If playback fails due to CORS, set PROXY_BASE in env and redeploy.)"
        update.message.reply_text(msg)
    else:
        update.message.reply_text(
            "No direct mp4/m3u8 URL found on the page. The page might be JS-rendered or protected.\n"
            "If you want, deploy a headless scraper (Puppeteer) in the same service and I'll try again."
        )

def error_handler(update: object, context: CallbackContext):
    logger.error("Update caused error: %s", context.error)

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_error_handler(error_handler)

    logger.info("Starting Telegram bot (polling)...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
