import os
import random
import logging
import asyncio
import json
from threading import Thread

from flask import Flask

import firebase_admin
from firebase_admin import credentials, db

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import RetryAfter
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from dotenv import load_dotenv


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

OWNER_ID = int(os.getenv("OWNER_ID", "8223664417"))

IMAGE_URL = os.getenv(
    "IMAGE_URL",
    "https://telegra.ph/file/07f45aef0cc6323c21c78.jpg"
)

SUPPORT_URL = os.getenv(
    "SUPPORT_URL",
    "https://t.me/Jr_Auto_ReactionBot"
)


# =========================================================
# FLASK SERVER — RENDER
# =========================================================

app_flask = Flask(__name__)


@app_flask.route("/")
def home():
    return "⟨ 𝐉𝐑 ⟩ 𝐌𝐮𝐥𝐭𝐢 𝐑𝐞𝐚𝐜𝐭𝐢𝐨𝐧 🌹 is online and running! 🚀"


@app_flask.route("/health")
def health():
    return "OK"


def run_server():
    port = int(os.environ.get("PORT", "10000"))

    app_flask.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


Thread(
    target=run_server,
    daemon=True
).start()


# =========================================================
# DEFAULT REACTIONS
# =========================================================

DEFAULT_EMOJIS = [
    "👍",
    "👎",
    "❤️",
    "🔥",
    "🥰",
    "👏",
    "😁",
    "🤔",
    "🤯",
    "😱",
    "🎉",
    "🤩",
    "🙏",
    "👌",
    "❤️‍🔥",
    "💯",
    "🤣",
    "⚡",
    "🏆",
    "😈",
]


# =========================================================
# FIREBASE
# =========================================================

firebase_initialized = False


def init_firebase():
    global firebase_initialized

    if firebase_initialized:
        return True

    database_url = os.getenv(
        "FIREBASE_DATABASE_URL",
        ""
    ).strip()

    service_account_json = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT_JSON",
        ""
    ).strip()

    if not database_url or not service_account_json:
        logger.warning(
            "Firebase credentials missing. "
            "Running without Firebase persistence."
        )
        return False

    try:
        service_account_data = json.loads(
            service_account_json
        )

        cred = credentials.Certificate(
            service_account_data
        )

        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": database_url
            }
        )

        firebase_initialized = True

        logger.info(
            "Firebase initialized successfully."
        )

        return True

    except Exception as e:
        logger.error(
            f"Firebase initialization failed: {e}"
        )

        return False


# =========================================================
# BOT TOKEN LOADER
# =========================================================

def get_tokens():
    tokens = []

    # Main token
    single_token = os.getenv("BOT_TOKEN")

    if single_token:
        single_token = single_token.strip()

        if single_token:
            tokens.append(
                (1, single_token)
            )

    # BOT_TOKEN_1 ... BOT_TOKEN_49
    for i in range(1, 50):

        token = os.getenv(
            f"BOT_TOKEN_{i}"
        )

        if token:
            token = token.strip()

            if token:
                tokens.append(
                    (i, token)
                )

    # Remove duplicate tokens
    unique_tokens = []
    seen = set()

    for index, token in tokens:

        if token not in seen:
            seen.add(token)

            unique_tokens.append(
                (index, token)
            )

    return unique_tokens


# =========================================================
# FIREBASE HELPERS
# =========================================================

def get_custom_reactions(chat_id):

    if not firebase_initialized:
        return None

    try:
        data = db.reference(
            f"custom_reactions/{chat_id}"
        ).get()

        if isinstance(data, list):

            valid = [
                str(emoji)
                for emoji in data
                if emoji
            ]

            if valid:
                return valid

    except Exception as e:
        logger.warning(
            f"Could not load custom reactions: {e}"
        )

    return None


def save_custom_reactions(
    chat_id,
    reactions
):

    if not firebase_initialized:
        return False

    try:
        db.reference(
            f"custom_reactions/{chat_id}"
        ).set(reactions)

        return True

    except Exception as e:
        logger.error(
            f"Could not save custom reactions: {e}"
        )

        return False


# =========================================================
# /START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_chat:
        return

    bot_username = (
        context.bot.username
        or "ReactionBot"
    )

    welcome_text = (
        "<b>⟨ 𝐉𝐑 ⟩ 𝐌𝐮𝐥𝐭𝐢 𝐑𝐞𝐚𝐜𝐭𝐢𝐨𝐧 🌹</b>\n\n"
        "✨ <b>Welcome!</b>\n\n"
        "অ্যাডমিন হিসেবে আমাকে আপনার "
        "চ্যানেল বা গ্রুপে যুক্ত করুন।\n\n"
        "📢 Channel/Group-এ নতুন পোস্ট এলে "
        "বট স্বয়ংক্রিয়ভাবে reaction দেওয়ার চেষ্টা করবে।\n\n"
        "⚙️ <b>Custom Reaction:</b>\n"
        "নিজের পছন্দের reaction সেট করতে "
        "<code>/set_reactions</code> ব্যবহার করুন।"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "➕ ADD TO CHANNEL",
                url=(
                    f"https://t.me/"
                    f"{bot_username}"
                    f"?startchannel=true"
                )
            ),

            InlineKeyboardButton(
                "➕ ADD TO GROUP",
                url=(
                    f"https://t.me/"
                    f"{bot_username}"
                    f"?startgroup=true"
                )
            ),
        ],

        [
            InlineKeyboardButton(
                "🌹 Support Channel",
                url=SUPPORT_URL
            )
        ],
    ]

    markup = InlineKeyboardMarkup(
        keyboard
    )

    try:

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=IMAGE_URL,
            caption=welcome_text,
            parse_mode="HTML",
            reply_markup=markup,
        )

    except Exception as e:

        logger.warning(
            f"Image message failed: {e}"
        )

        if update.message:

            await update.message.reply_text(
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=markup,
            )


# =========================================================
# /SET_REACTIONS
# =========================================================

async def set_reactions_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_chat:
        return

    chat = update.effective_chat

    if chat.type == "private":

        if update.message:
            await update.message.reply_text(
                "⚠️ এই command টি "
                "channel বা group-এ ব্যবহার করুন।"
            )

        return

    args = context.args

    if not args:

        if update.message:
            await update.message.reply_text(
                "❌ কোনো reaction দেওয়া হয়নি।\n\n"
                "উদাহরণ:\n"
                "<code>/set_reactions ❤️ 🔥 👍 🥰</code>",
                parse_mode="HTML",
            )

        return

    # Keep reasonable emoji input
    custom_emojis = []

    for emoji in args:

        emoji = emoji.strip()

        if not emoji:
            continue

        if len(emoji) <= 8:
            custom_emojis.append(emoji)

    # Remove duplicates
    custom_emojis = list(
        dict.fromkeys(custom_emojis)
    )

    if not custom_emojis:

        if update.message:
            await update.message.reply_text(
                "❌ Valid reaction পাওয়া যায়নি।"
            )

        return

    chat_id = str(chat.id)

    saved = save_custom_reactions(
        chat_id,
        custom_emojis
    )

    if saved:

        text = (
            "✅ <b>Custom Reactions Saved!</b>\n\n"
            f"🎯 {' '.join(custom_emojis)}"
        )

    else:

        text = (
            "⚠️ Reaction list এই runtime-এর জন্য "
            "set হয়েছে, কিন্তু Firebase-এ save হয়নি।\n\n"
            f"🎯 {' '.join(custom_emojis)}"
        )

    if update.message:

        await update.message.reply_text(
            text,
            parse_mode="HTML"
        )


# =========================================================
# HANDLE CHANNEL / GROUP POSTS
# =========================================================

async def handle_incoming(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    target = (
        update.channel_post
        or update.message
    )

    if not target:
        return

    if not update.effective_chat:
        return

    chat_id = str(
        update.effective_chat.id
    )

    # Load custom reactions
    custom_emojis = get_custom_reactions(
        chat_id
    )

    if custom_emojis:
        allowed_emojis = custom_emojis
    else:
        allowed_emojis = DEFAULT_EMOJIS

    if not allowed_emojis:
        logger.warning(
            f"No reactions available for {chat_id}"
        )
        return

    # Small random delay
    await asyncio.sleep(
        random.uniform(0.1, 0.8)
    )

    selected_emoji = random.choice(
        allowed_emojis
    )

    try:

        await context.bot.set_message_reaction(
            chat_id=target.chat_id,
            message_id=target.message_id,
            reaction=selected_emoji,
            is_big=True,
        )

        logger.info(
            f"Reaction {selected_emoji} "
            f"added to message "
            f"{target.message_id} "
            f"in {chat_id}"
        )

    except RetryAfter as e:

        retry_seconds = int(
            getattr(
                e,
                "retry_after",
                1
            )
        )

        logger.warning(
            f"FloodWait/RetryAfter: "
            f"waiting {retry_seconds}s"
        )

        await asyncio.sleep(
            retry_seconds
        )

        try:

            await context.bot.set_message_reaction(
                chat_id=target.chat_id,
                message_id=target.message_id,
                reaction=selected_emoji,
                is_big=True,
            )

            logger.info(
                f"Retry successful: "
                f"{selected_emoji}"
            )

        except Exception as retry_error:

            logger.warning(
                f"Retry reaction failed: "
                f"{retry_error}"
            )

    except Exception as e:

        logger.warning(
            f"Reaction failed for "
            f"message {target.message_id}: {e}"
        )


# =========================================================
# BOT BUILDER
# =========================================================

async def build_bot(
    token_index,
    token
):

    application = (
        Application
        .builder()
        .token(token)
        .concurrent_updates(True)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "set_reactions",
            set_reactions_command
        )
    )

    # Channel posts
    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            handle_incoming
        )
    )

    # Group messages
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & ~filters.COMMAND,
            handle_incoming
        )
    )

    return application


# =========================================================
# MAIN ENGINE
# =========================================================

async def main():

    logger.info(
        "Initializing Multi-Reaction Engine..."
    )

    # Firebase
    init_firebase()

    # Tokens
    tokens = get_tokens()

    if not tokens:

        logger.error(
            "No BOT_TOKEN or BOT_TOKEN_1... "
            "found in environment variables!"
        )

        return

    logger.info(
        f"Found {len(tokens)} bot token(s)."
    )

    running_apps = []

    # Start every bot
    for token_index, token in tokens:

        try:

            application = await build_bot(
                token_index,
                token
            )

            await application.initialize()
            await application.start()

            if application.updater:

                await application.updater.start_polling(
                    drop_pending_updates=True
                )

                running_apps.append(
                    application
                )

                try:

                    bot_info = (
                        await application.bot.get_me()
                    )

                    logger.info(
                        f"Bot #{token_index} "
                        f"running as "
                        f"@{bot_info.username}"
                    )

                except Exception:

                    logger.info(
                        f"Bot #{token_index} "
                        f"started successfully."
                    )

        except Exception as e:

            logger.error(
                f"Failed to start Bot "
                f"#{token_index}: {e}"
            )

    if not running_apps:

        logger.error(
            "No bot could be started."
        )

        return

    logger.info(
        f"{len(running_apps)} bot(s) "
        "are now running."
    )

    # Keep process alive
    try:

        await asyncio.Event().wait()

    finally:

        logger.info(
            "Shutting down bots..."
        )

        for application in running_apps:

            try:

                if application.updater:
                    await application.updater.stop()

                await application.stop()
                await application.shutdown()

            except Exception as e:

                logger.warning(
                    f"Shutdown error: {e}"
                )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        logger.info(
            "Bot stopped manually."
        )
