import os
import re
import json
import asyncio
import firebase_admin
from firebase_admin import credentials, db
from pyrogram import Client, filters, enums, idle
from pyrogram.raw import functions

# ----------------- ENVIRONMENT VARIABLES ----------------- #
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
FIREBASE_URL = os.getenv("FIREBASE_URL", "")
FIREBASE_CRED_JSON = os.getenv("FIREBASE_CRED", "")  # Full JSON string of Firebase credentials

# ADMIN AUTHORIZATION (আপনার টেলিগ্রাম আইডি)
ADMIN_IDS = [8223664417]

# Env থেকে অতিরিক্ত অ্যাডমিন আইডি যুক্ত করার অপশন (ইচ্ছা হলে)
env_admins = os.getenv("ADMIN_IDS", "")
if env_admins:
    for x in env_admins.split(","):
        if x.strip().isdigit():
            ADMIN_IDS.append(int(x.strip()))

# ----------------- FIREBASE INITIALIZATION ----------------- #
try:
    cred_dict = json.loads(FIREBASE_CRED_JSON)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_URL
    })
    print("✅ Firebase initialized successfully!")
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")

# ----------------- BOT CLIENT ----------------- #
bot = Client(
    "reaction_view_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# User state storage for multi-step input
user_data = {}

# Helper: Fetch all sessions from Firebase
def get_sessions():
    ref = db.reference('sessions')
    sessions = ref.get()
    if isinstance(sessions, dict):
        return list(sessions.values())
    elif isinstance(sessions, list):
        return [s for s in sessions if s]
    return []

# Helper: Save session to Firebase
def add_session_to_db(session_str):
    ref = db.reference('sessions')
    ref.push(session_str)

# Helper: Telegram Link Parser
def parse_tg_link(link: str):
    pattern_private = r"https://t\.me/c/(\d+)/(\d+)"
    pattern_public = r"https://t\.me/([^/]+)/(\d+)"
    
    match_private = re.match(pattern_private, link)
    if match_private:
        chat_id = int(f"-100{match_private.group(1)}")
        msg_id = int(match_private.group(2))
        return chat_id, msg_id
        
    match_public = re.match(pattern_public, link)
    if match_public:
        chat_id = match_public.group(1)
        msg_id = int(match_public.group(2))
        return chat_id, msg_id
        
    return None, None

# Helper: Admin Check
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ----------------- BOT HANDLERS ----------------- #

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.reply_text("❌ **Access Denied!** আপনি এই বোট ব্যবহারের জন্য অনুমোদিত নন।")
        return

    user_data[user_id] = {"step": "WAITING_LINK"}
    total_sessions = len(get_sessions())
    
    await message.reply_text(
        f"👋 **Reaction & View Bot-এ স্বাগতম! (Admin Panel)**\n\n"
        f"📊 **ডাটাবেজে মোট সেশন আছে:** `{total_sessions}` টি\n\n"
        f"কাজ শুরু করতে আপনার **চ্যানেল বা পোস্টের লিঙ্ক** দিন:"
    )

@bot.on_message(filters.command("addsession"))
async def add_session_cmd(client, message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.reply_text("❌ **Access Denied!** শুধু অ্যাডমিন সেশন যুক্ত করতে পারবে।")
        return

    try:
        session_str = message.text.split(" ", 1)[1].strip()
        add_session_to_db(session_str)
        total_sessions = len(get_sessions())
        await message.reply_text(
            f"✅ **নতুন Session String ফায়ারবেসে যুক্ত করা হয়েছে!**\n"
            f"📊 বর্তমান মোট সেশন: `{total_sessions}` টি"
        )
    except IndexError:
        await message.reply_text("⚠️ **সঠিক নিয়ম:** `/addsession <your_session_string>`")

@bot.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.reply_text("❌ **Access Denied!**")
        return

    total = len(get_sessions())
    await message.reply_text(f"📊 **ফায়ারবেসে মোট সেশন সংখ্যা:** `{total}`")

@bot.on_message(filters.text & filters.private)
async def handle_steps(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Check Admin
    if not is_admin(user_id):
        return

    # Ignore commands
    if text.startswith("/"):
        return
        
    if user_id not in user_data or "step" not in user_data[user_id]:
        await message.reply_text("কমান্ড রি-স্টার্ট করতে /start চাপুন।")
        return

    step = user_data[user_id]["step"]

    # STEP 1: Link Input
    if step == "WAITING_LINK":
        chat_id, msg_id = parse_tg_link(text)
        if not chat_id:
            await message.reply_text("❌ অবৈধ লিঙ্ক! সঠিক চ্যানেল/গ্রুপ পোস্ট লিঙ্ক দিন (যেমন: https://t.me/channel/123)।")
            return
            
        user_data[user_id]["link"] = text
        user_data[user_id]["chat_id"] = chat_id
        user_data[user_id]["msg_id"] = msg_id
        user_data[user_id]["step"] = "WAITING_VIEWS"
        
        await message.reply_text("👁️ কতগুলো **View** প্রয়োজন? (সংখ্যায় লিখুন, যেমন: 50):")

    # STEP 2: Views Input
    elif step == "WAITING_VIEWS":
        if not text.isdigit():
            await message.reply_text("❌ অনুগ্রহ করে শুধু সংখ্যা লিখুন।")
            return
            
        views = int(text)
        total_sessions = len(get_sessions())
        
        if views > total_sessions:
            await message.reply_text(f"⚠️ ডাটাবেজে মাত্র `{total_sessions}` টি সেশন আছে! এর বেশি ভিউ দেওয়া সম্ভব নয়।")
            return

        user_data[user_id]["views"] = views
        user_data[user_id]["step"] = "WAITING_REACTIONS"
        
        await message.reply_text(
            f"👍 কতগুলো **Reaction** প্রয়োজন? (সর্বোচ্চ `{views}` টি দেওয়া যাবে, শুধু View চাইলে 0 লিখুন):"
        )

    # STEP 3: Reactions Input & Validation
    elif step == "WAITING_REACTIONS":
        if not text.isdigit():
            await message.reply_text("❌ অনুগ্রহ করে শুধু সংখ্যা লিখুন।")
            return
            
        reactions = int(text)
        views = user_data[user_id]["views"]
        
        # Validation: Reaction Views এর চেয়ে বেশি হতে পারবে না
        if reactions > views:
            await message.reply_text(
                f"❌ **ভুল ইনপুট!**\n"
                f"Reaction (`{reactions}`) কখনো View (`{views}`) এর চেয়ে বেশি হতে পারবে না।\n"
                f"অনুগ্রহ করে `{views}` বা তার কম সংখ্যা ইনপুট দিন:"
            )
            return

        user_data[user_id]["reactions"] = reactions
        
        if reactions == 0:
            # View only mode
            await start_execution(client, message, user_id, emoji=None)
        else:
            user_data[user_id]["step"] = "WAITING_EMOJI"
            await message.reply_text("😍 কোন Emoji রিঅ্যাকশন দিতে চান? (যেমন: 👍, 🔥, ❤️, 🥰):")

    # STEP 4: Emoji Input & Run
    elif step == "WAITING_EMOJI":
        emoji = text
        await start_execution(client, message, user_id, emoji=emoji)

# ----------------- EXECUTION LOGIC ----------------- #

async def start_execution(client, message, user_id, emoji=None):
    data = user_data.get(user_id)
    chat_id = data["chat_id"]
    msg_id = data["msg_id"]
    views = data["views"]
    reactions = data["reactions"]
    
    # State reset
    user_data[user_id] = {}

    status_msg = await message.reply_text("⏳ কাজ প্রসেস হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...")
    
    sessions = get_sessions()
    
    # Check if chat is Group or Channel
    is_group = False
    try:
        chat_info = await client.get_chat(chat_id)
        if chat_info.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            is_group = True
    except Exception:
        pass

    success_views = 0
    success_reactions = 0

    for i in range(views):
        session_str = sessions[i]
        do_react = (i < reactions)
        
        try:
            async with Client(f"temp_userbot_{i}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True) as ub:
                
                # ১. চ্যানেল হলে ভিউ করবে
                if not is_group:
                    try:
                        await ub.read_chat_history(chat_id)
                        peer = await ub.resolve_peer(chat_id)
                        await ub.invoke(
                            functions.messages.GetMessagesViews(
                                peer=peer,
                                id=[msg_id],
                                increment=True
                            )
                        )
                        success_views += 1
                    except Exception:
                        pass
                
                # ২. রিঅ্যাকশন হ্যান্ডলিং (গ্রুপ ও চ্যানেল উভয়ের জন্য)
                if do_react and emoji:
                    try:
                        await ub.send_reaction(chat_id, msg_id, emoji)
                        success_reactions += 1
                        if is_group:
                            success_views += 1 # গ্রুপে রিঅ্যাকশন দিলেই অটো ভিউ ধরা হচ্ছে
                    except Exception:
                        pass

        except Exception as e:
            print(f"Session {i} Error: {e}")

        await asyncio.sleep(0.3) # Rate limit এড়াতে ছোট বিরতি

    # ফাইনাল রিপোর্ট
    report = "✅ **কাজ সম্পন্ন হয়েছে!**\n\n"
    if is_group:
        report += f"👥 **টাইপ:** গ্রুপ (গ্রুপে আলাদা ভিউ কাউন্টার নেই)\n"
        report += f"👍 **সাফল্য রিঅ্যাকশন:** `{success_reactions}/{reactions}`"
    else:
        report += f"📢 **টাইপ:** চ্যানেল\n"
        report += f"👁️ **সাফল্য ভিউ:** `{success_views}/{views}`\n"
        report += f"👍 **সাফল্য রিঅ্যাকশন:** `{success_reactions}/{reactions}`"

    await status_msg.edit_text(report)

# ----------------- MODERN ASYNC RUNNER ----------------- #
async def main():
    await bot.start()
    print("✅ Bot started successfully!")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
