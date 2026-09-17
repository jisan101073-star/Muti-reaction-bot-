import os
import re
import json
import asyncio

# ----------------- CRITICAL FIX FOR PYTHON 3.14+ ----------------- #
# Pyrogram বা অন্য কিছু ইমপোর্ট করার আগেই সরাসরি নতুন Event Loop সেট করতে হবে
# কোনো get_event_loop() ব্যবহার করা যাবে না
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ----------------------------------------------------------------- #
import firebase_admin
from firebase_admin import credentials, db
from pyrogram import Client, filters, enums, idle
from pyrogram.raw import functions

# ----------------- ENVIRONMENT VARIABLES ----------------- #
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
FIREBASE_URL = os.getenv("FIREBASE_URL", "")
FIREBASE_CRED_JSON = os.getenv("FIREBASE_CRED", "")  # Full JSON string

# ADMIN AUTHORIZATION
ADMIN_IDS = [8223664417]

env_admins = os.getenv("ADMIN_IDS", "")
if env_admins:
    for x in env_admins.split(","):
        if x.strip().isdigit():
            ADMIN_IDS.append(int(x.strip()))

# ----------------- FIREBASE INITIALIZATION ----------------- #
try:
    if FIREBASE_CRED_JSON:
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

def get_sessions():
    ref = db.reference('sessions')
    sessions = ref.get()
    if isinstance(sessions, dict):
        return list(sessions.values())
    elif isinstance(sessions, list):
        return [s for s in sessions if s]
    return []

def add_session_to_db(session_str):
    ref = db.reference('sessions')
    ref.push(session_str)

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

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ----------------- BOT HANDLERS ----------------- #
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.reply_text("❌ **Access Denied!**")
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
    if not is_admin(user_id): return
    try:
        session_str = message.text.split(" ", 1)[1].strip()
        add_session_to_db(session_str)
        total_sessions = len(get_sessions())
        await message.reply_text(f"✅ **নতুন Session String যুক্ত করা হয়েছে!**\n📊 সেশন: `{total_sessions}` টি")
    except IndexError:
        await message.reply_text("⚠️ **সঠিক নিয়ম:** `/addsession <your_session_string>`")

@bot.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    total = len(get_sessions())
    await message.reply_text(f"📊 **ফায়ারবেসে মোট সেশন সংখ্যা:** `{total}`")

@bot.on_message(filters.text & filters.private)
async def handle_steps(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not is_admin(user_id) or text.startswith("/"): return
        
    if user_id not in user_data or "step" not in user_data[user_id]:
        await message.reply_text("কমান্ড রি-স্টার্ট করতে /start চাপুন।")
        return

    step = user_data[user_id]["step"]

    if step == "WAITING_LINK":
        chat_id, msg_id = parse_tg_link(text)
        if not chat_id:
            await message.reply_text("❌ অবৈধ লিঙ্ক!")
            return
        user_data[user_id].update({"link": text, "chat_id": chat_id, "msg_id": msg_id, "step": "WAITING_VIEWS"})
        await message.reply_text("👁️ কতগুলো **View** প্রয়োজন? (সংখ্যায় লিখুন):")

    elif step == "WAITING_VIEWS":
        if not text.isdigit(): return await message.reply_text("❌ সংখ্যা লিখুন।")
        views = int(text)
        total_sessions = len(get_sessions())
        if views > total_sessions:
            return await message.reply_text(f"⚠️ ডাটাবেজে মাত্র `{total_sessions}` টি সেশন আছে!")
        user_data[user_id].update({"views": views, "step": "WAITING_REACTIONS"})
        await message.reply_text(f"👍 কতগুলো **Reaction** প্রয়োজন? (সর্বোচ্চ `{views}`, শুধু View চাইলে 0 লিখুন):")

    elif step == "WAITING_REACTIONS":
        if not text.isdigit(): return await message.reply_text("❌ সংখ্যা লিখুন।")
        reactions = int(text)
        views = user_data[user_id]["views"]
        if reactions > views:
            return await message.reply_text(f"❌ Reaction `{reactions}` কখনো View `{views}` এর বেশি হতে পারবে না।")
        user_data[user_id]["reactions"] = reactions
        
        if reactions == 0:
            await start_execution(client, message, user_id, emoji=None)
        else:
            user_data[user_id]["step"] = "WAITING_EMOJI"
            await message.reply_text("😍 কোন Emoji রিঅ্যাকশন দিতে চান? (যেমন: 👍, 🔥, ❤️):")

    elif step == "WAITING_EMOJI":
        await start_execution(client, message, user_id, emoji=text)

# ----------------- EXECUTION LOGIC ----------------- #
async def start_execution(client, message, user_id, emoji=None):
    data = user_data.get(user_id)
    chat_id, msg_id, views, reactions = data["chat_id"], data["msg_id"], data["views"], data["reactions"]
    user_data[user_id] = {}
    status_msg = await message.reply_text("⏳ কাজ প্রসেস হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...")
    
    sessions = get_sessions()
    is_group = False
    try:
        chat_info = await client.get_chat(chat_id)
        if chat_info.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]: is_group = True
    except: pass

    success_views, success_reactions = 0, 0

    for i in range(views):
        session_str = sessions[i]
        do_react = (i < reactions)
        try:
            async with Client(f"temp_ub_{i}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True) as ub:
                if not is_group:
                    try:
                        await ub.read_chat_history(chat_id)
                        peer = await ub.resolve_peer(chat_id)
                        await ub.invoke(functions.messages.GetMessagesViews(peer=peer, id=[msg_id], increment=True))
                        success_views += 1
                    except: pass
                
                if do_react and emoji:
                    try:
                        await ub.send_reaction(chat_id, msg_id, emoji)
                        success_reactions += 1
                        if is_group: success_views += 1 
                    except: pass
        except Exception as e:
            print(f"Session {i} Error: {e}")
        await asyncio.sleep(0.3) 

    report = "✅ **কাজ সম্পন্ন হয়েছে!**\n\n"
    if is_group:
        report += f"👥 **টাইপ:** গ্রুপ\n👍 **সাফল্য রিঅ্যাকশন:** `{success_reactions}/{reactions}`"
    else:
        report += f"📢 **টাইপ:** চ্যানেল\n👁️ **সাফল্য ভিউ:** `{success_views}/{views}`\n👍 **সাফল্য রিঅ্যাকশন:** `{success_reactions}/{reactions}`"
    await status_msg.edit_text(report)

# ----------------- MAIN RUNNER ----------------- #
async def main():
    await bot.start()
    print("✅ Bot started successfully!")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    # শুরুতেই যে লুপ তৈরি করা হয়েছিল, সেটিতেই বোট রান করানো হচ্ছে
    loop.run_until_complete(main())
