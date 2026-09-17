import os
import random
import logging
import asyncio
import time
import html
import json
import copy
from threading import Thread

from flask import Flask

import firebase_admin
from firebase_admin import credentials, db

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import RetryAfter
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

# =========================================================
# CONFIG & FLASK SERVER FOR RENDER
# =========================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

OWNER_ID = int(os.getenv("OWNER_ID", "8223664417"))
IMAGE_URL = os.getenv("IMAGE_URL", "https://telegra.ph/file/07f45aef0cc6323c21c78.jpg")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/Jr_Auto_ReactionBot")

# Render Port Binding Web Server
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Multi-Reaction Bot is online and running! 🚀"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)

# Start Flask immediately to avoid Render Port Timeout
Thread(target=run_server, daemon=True).start()

# Default Reactions
DEFAULT_EMOJIS = [
    "👍", "👎", "❤️", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱",
    "🎉", "🤩", "🙏", "👌", "❤️‍🔥", "💯", "🤣", "⚡", "🏆", "😈"
]

# =========================================================
# FIREBASE & DATABASE
# =========================================================

firebase_initialized = False

def init_firebase():
    global firebase_initialized
    if firebase_initialized:
        return

    database_url = os.getenv("FIREBASE_DATABASE_URL", "").strip()
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

    if not database_url or not service_account_json:
        logger.warning("Firebase credentials missing. Running in local memory mode.")
        return

    try:
        service_account_data = json.loads(service_account_json)
        cred = credentials.Certificate(service_account_data)
        firebase_admin.initialize_app(cred, {"databaseURL": database_url})
        firebase_initialized = True
        logger.info("Firebase initialized successfully.")
    except Exception as e:
        logger.error(f"Firebase init error: {e}")

def get_tokens():
    tokens = []
    single_token = os.getenv("BOT_TOKEN")
    if single_token and single_token.strip():
        tokens.append((1, single_token.strip()))

    for i in range(1, 50):
        token = os.getenv(f"BOT_TOKEN_{i}")
        if token and token.strip():
            tokens.append((i, token.strip()))

    unique_tokens = []
    seen = set()
    for idx, tok in tokens:
        if tok not in seen:
            seen.add(tok)
            unique_tokens.append((idx, tok))

    return unique_tokens

# =========================================================
# BOT HANDLERS & MULTI-REACTION
# =========================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    bot_username = context.bot.username or "ReactionBot"
    welcome_text = (
        f"<b>Hey! Welcome to Multi-Reaction Bot</b> 👋\n\n"
        f"অ্যাডমিন হিসেবে আমাকে এবং আমার অ্যাসিস্ট্যান্ট বটগুলোকে আপনার চ্যানেলে যুক্ত করুন।\n"
        f"নতুন পোস্ট হওয়ার সাথে সাথে অটোমেটিক মাল্টিপল রিঅ্যাকশন যুক্ত হবে! ✨"
    )

    keyboard = [
        [
            InlineKeyboardButton("ADD TO CHANNEL", url=f"https://t.me/{bot_username}?startchannel=true"),
            InlineKeyboardButton("ADD TO GROUP", url=f"https://t.me/{bot_username}?startgroup=true")
        ],
        [InlineKeyboardButton("Support Channel", url=SUPPORT_URL)]
    ]

    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=IMAGE_URL,
            caption=welcome_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        await update.message.reply_text(
            text=welcome_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def set_reactions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কাস্টম ইমোজি সেট করার কমান্ড: /set_reactions ❤️ 🔥 👍"""
    if not update.effective_chat or update.effective_chat.type == "private":
        await update.message.reply_text("এই কমান্ডটি চ্যানেলে বা গ্রুপে ব্যবহার করুন।")
        return

    args = context.args
    if not args:
        await update.message.reply_text("ইমোজি উল্লেখ করুন। উদাহরণ: <code>/set_reactions ❤️ 🔥 👍</code>", parse_mode="HTML")
        return

    chat_id = str(update.effective_chat.id)
    custom_emojis = [e for e in args if len(e) <= 4] # Basic emoji filtering

    if firebase_initialized:
        db.reference(f"custom_reactions/{chat_id}").set(custom_emojis)

    await update.message.reply_text(f"✅ কাস্টম রিঅ্যাকশন সেট করা হয়েছে: {' '.join(custom_emojis)}")

async def handle_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.channel_post or update.message
    if not target or not update.effective_chat:
        return

    chat_id = str(update.effective_chat.id)
    allowed_emojis = DEFAULT_EMOJIS

    # Firebase থেকে কাস্টম ইমোজি লোড করার চেষ্টা
    if firebase_initialized:
        try:
            custom_data = db.reference(f"custom_reactions/{chat_id}").get()
            if custom_data and isinstance(custom_data, list):
                allowed_emojis = custom_data
        except Exception as e:
            logger.warning(f"Failed to fetch custom reactions: {e}")

    await asyncio.sleep(random.uniform(0.1, 0.8))
    selected_emoji = random.choice(allowed_emojis)

    try:
        await context.bot.set_message_reaction(
            chat_id=target.chat_id,
            message_id=target.message_id,
            reaction=selected_emoji,
            is_big=True
        )
    except RetryAfter as e:
        await asyncio.sleep(int(e.retry_after))
        try:
            await context.bot.set_message_reaction(
                chat_id=target.chat_id,
                message_id=target.message_id,
                reaction=selected_emoji,
                is_big=True
            )
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Reaction failed: {e}")

# =========================================================
# BOT BUILDER & ENGINE
# =========================================================

async def build_bot(token_index, token):
    app = Application.builder().token(token).concurrent_updates(True).build()
    await app.initialize()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("set_reactions", set_reactions_command))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL | filters.ChatType.GROUPS, handle_incoming))

    return app

async def main():
    init_firebase()
    tokens = get_tokens()

    if not tokens:
        logger.error("No BOT_TOKEN or BOT_TOKEN_1 found in environment variables!")
        return

    logger.info(f"Starting Multi-Bot Engine with {len(tokens)} token(s)...")
    apps = []

    for token_index, token in tokens:
        try:
            app = await build_bot(token_index, token)
            await app.start()

            if app.updater:
                await app.updater.start_polling(drop_pending_updates=True)
                apps.append(app)
                logger.info(f"Bot #{token_index} running as @{app.bot.username}")
        except Exception as e:
            logger.error(f"Failed to start Bot #{token_index}: {e}")

    if apps:
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
