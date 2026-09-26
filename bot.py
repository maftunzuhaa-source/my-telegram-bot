import asyncio
import json
import os
import html
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# ==================== CONFIG ====================
BOT_TOKEN = "8632335432:AAF6fThMY_2pLqXID4562EzFKR_iAiXHgFk"          # ← এখানে তোমার বট টোকেন দাও
ADMINS = [8645151760]                      # ← এখানে তোমার টেলিগ্রাম আইডি দাও

# Files
USER_DATA_FILE = "users.json"
STATS_FILE = "user_stats.json"
BANNED_USERS_FILE = "banned_users.json"
SYS_CONFIG_FILE = "sys_config.json"
API_PROVIDERS_FILE = "api_providers.json"

# Settings
OTP_RATE = 0.20
REFERRAL_PRICE = 0.20
MIN_WITHDRAW = 30.0

# ==================== HELPERS ====================
def load_data(filename, default=None):
    if default is None:
        default = {}
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_data(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_sys_config():
    default = {
        "official_channel_id": -1001234567890,
        "official_channel_link": "https://t.me/yourchannel",
        "otp_group_id": -1001234567890,
        "otp_group_link": "https://t.me/your_otp_group",
    }
    data = load_data(SYS_CONFIG_FILE, default)
    for k, v in default.items():
        if k not in data:
            data[k] = v
    save_data(data, SYS_CONFIG_FILE)
    return data

def get_user(uid, full_name=None, username=None):
    uid = str(uid)
    data = load_data(USER_DATA_FILE)
    if uid not in data:
        data[uid] = {
            "user_id": uid,
            "balance": 0.0,
            "referral_count": 0,
            "full_name": full_name or "",
            "username": username or "",
        }
    else:
        if full_name:
            data[uid]["full_name"] = full_name
        if username:
            data[uid]["username"] = username
    save_data(data, USER_DATA_FILE)
    return data[uid]

def is_admin(uid):
    return uid in ADMINS

def is_user_banned(uid):
    banned = load_data(BANNED_USERS_FILE, [])
    return str(uid) in banned

def get_global_stats():
    stats = load_data(STATS_FILE)
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)
    today_n = today_o = 0
    for u in stats.values():
        for t in u.get("numbers_taken", []):
            if datetime.fromisoformat(t) >= today:
                today_n += 1
        for t in u.get("otps_received", []):
            if datetime.fromisoformat(t) >= today:
                today_o += 1
    return today_n, today_o

# ==================== KEYBOARDS ====================
def main_keyboard(uid):
    kb = [
        [KeyboardButton("📱 GET NUMBER"), KeyboardButton("🔍 Search Number")],
        [KeyboardButton("📊 TRAFFIC"), KeyboardButton("🔐 2FA ONLINE")],
        [KeyboardButton("🎁 Refer"), KeyboardButton("💳 WITHDRAWAL")],
        [KeyboardButton("👤 SUPPORT")]
    ]
    if is_admin(uid):
        kb.append([KeyboardButton("⚙️ OWNER PANEL")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)

def owner_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔌 Number Api Setting", callback_data="owner_number_api")],
        [
            InlineKeyboardButton("📢 BROADCAST", callback_data="owner_broadcast"),
            InlineKeyboardButton("🔔 FORCE JOIN", callback_data="owner_force_join")
        ],
        [
            InlineKeyboardButton("📨 OTP GROUP", callback_data="owner_otp_group"),
            InlineKeyboardButton("👥 USER CONTROL", callback_data="owner_user_control")
        ],
        [InlineKeyboardButton("⚙️ Panel Control", callback_data="owner_panel_control")],
        [InlineKeyboardButton("📝 CUSTOMIZE TEXTS & BUTTONS", callback_data="owner_customizer")],
        [InlineKeyboardButton("📤 UPLOAD FIREBASE", callback_data="owner_upload_firebase")],
        [InlineKeyboardButton("🟢 FIREBASE ACTIVE", callback_data="owner_firebase_active")],
        [InlineKeyboardButton("❌ CLOSE", callback_data="close_menu")]
    ])

def number_api_keyboard():
    providers = load_data(API_PROVIDERS_FILE, [])
    buttons = []

    auto_on = any(p.get("auto", False) for p in providers)
    auto_text = "AUTO MODE: ON" if auto_on else "AUTO MODE: OFF"
    buttons.append([InlineKeyboardButton(auto_text, callback_data="api_toggle_auto")])

    active = sum(1 for p in providers if p.get("active", True))
    buttons.append([InlineKeyboardButton(f"Active Providers: {active}/20", callback_data="none")])

    for i, p in enumerate(providers):
        name = p.get("name", "Unknown")
        key = p.get("api_key", "")
        short = (key[:4] + "..." + key[-4:]) if len(key) > 8 else key or "NoKey"
        status = "✅" if p.get("active", True) else "❌"
        buttons.append([
            InlineKeyboardButton(f"{status} {name} ({short})", callback_data=f"api_toggle_{i}"),
            InlineKeyboardButton("🗑", callback_data=f"api_delete_{i}")
        ])

    buttons.append([InlineKeyboardButton("➕ Add New Provider (API)", callback_data="api_add_new")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="owner_back")])
    return InlineKeyboardMarkup(buttons)

# ==================== FORCE JOIN ====================
async def check_membership(bot, user_id, chat_id):
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

async def check_force_join(bot, user_id):
    sc = load_sys_config()
    ch = await check_membership(bot, user_id, sc["official_channel_id"])
    gr = await check_membership(bot, user_id, sc["otp_group_id"])
    return ch and gr

async def show_force_join(update, context, uid):
    sc = load_sys_config()
    text = (
        "🔔 <b>JOIN REQUIRED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "বট ব্যবহার করতে নিচের <b>২টা জায়গায়</b> জয়েন করো:\n\n"
        "1️⃣ Official Channel\n"
        "2️⃣ OTP Group"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=sc["official_channel_link"])],
        [InlineKeyboardButton("📨 Join OTP Group", url=sc["otp_group_link"])],
        [InlineKeyboardButton("✅ I Have Joined", callback_data="verify_join")]
    ])
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# ==================== WELCOME ====================
async def send_welcome(uid, context):
    try:
        chat = await context.bot.get_chat(uid)
        name = html.escape(chat.full_name or chat.first_name or "User")
    except:
        name = "User"
    text = (
        f"👋 <b>Welcome {name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚀 You have successfully joined the bot.\n"
        f"📱 Now you can get Number & OTP.\n\n"
        f"💎 Enjoy Premium Service!"
    )
    await context.bot.send_message(uid, text, parse_mode="HTML", reply_markup=main_keyboard(uid))

# ==================== OWNER PANEL ====================
async def show_owner_panel(update, context):
    today_n, today_o = get_global_stats()
    total_users = len(load_data(USER_DATA_FILE))
    text = (
        f"📊 <b>OWNER ZONE</b> 📊\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>DATABASE OVERVIEW</b>\n"
        f"--------------------\n"
        f"👤 <b>TOTAL USER</b>  » <code>{total_users}</code>\n"
        f"📱 <b>TODAY NUMBER</b> » <code>{today_n}</code>\n"
        f"🔑 <b>TODAY OTP</b>    » <code>{today_o}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    kb = owner_panel_keyboard()
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def show_number_api(update, context):
    text = (
        "🔑 <b>NUMBER API SETTING</b>\n"
        "Add Voltex / Stex / IVA / Lamix etc.\n"
        "Max 20 providers working together:"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=number_api_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=number_api_keyboard())

# ==================== LEADERBOARD ====================
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        return await update.message.reply_text("🛑 YOU ARE BANNED!")

    stats = load_data(STATS_FILE)
    users = load_data(USER_DATA_FILE)
    today = datetime(datetime.now().year, datetime.now().month, datetime.now().day)

    ranking = []
    for uid_str, st in stats.items():
        count = sum(1 for t in st.get("otps_received", []) if datetime.fromisoformat(t) >= today)
        if count > 0:
            name = users.get(uid_str, {}).get("full_name") or users.get(uid_str, {}).get("username") or f"User{uid_str}"
            ranking.append((html.escape(name), count))

    ranking.sort(key=lambda x: x[1], reverse=True)
    top = ranking[:10]

    text = "🏆 <b>TOP 10 OTP LEADERBOARD</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not top:
        text += "🛑 No OTP received today."
    else:
        for i, (name, cnt) in enumerate(top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} <b>{name}</b> → 🔑 <code>{cnt}</code>\n"
        text += "\n━━━━━━━━━━━━━━━━━━━━\nResets every midnight"

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard(uid))

# ==================== START ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user
    get_user(uid, full_name=user.full_name, username=user.username)

    if is_user_banned(uid):
        return await update.message.reply_text("🛑 YOU ARE BANNED!")

    if not is_admin(uid):
        if not await check_force_join(context.bot, uid):
            return await show_force_join(update, context, uid)

    await send_welcome(uid, context)

# ==================== CALLBACK ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data == "close_menu":
        try:
            await query.message.delete()
        except:
            pass
        return

    if data == "verify_join":
        if await check_force_join(context.bot, uid):
            await query.message.delete()
            await send_welcome(uid, context)
        else:
            await context.bot.send_message(uid, "❌ এখনো Channel বা OTP Group এ জয়েন করোনি!")
        return

    if data == "owner_back":
        await show_owner_panel(update, context)
        return

    if data == "owner_number_api":
        await show_number_api(update, context)
        return

    if data == "api_toggle_auto":
        providers = load_data(API_PROVIDERS_FILE, [])
        current = any(p.get("auto", False) for p in providers)
        for p in providers:
            p["auto"] = not current
        save_data(providers, API_PROVIDERS_FILE)
        await show_number_api(update, context)
        return

    if data.startswith("api_toggle_"):
        idx = int(data.split("_")[-1])
        providers = load_data(API_PROVIDERS_FILE, [])
        if 0 <= idx < len(providers):
            providers[idx]["active"] = not providers[idx].get("active", True)
            save_data(providers, API_PROVIDERS_FILE)
        await show_number_api(update, context)
        return

    if data.startswith("api_delete_"):
        idx = int(data.split("_")[-1])
        providers = load_data(API_PROVIDERS_FILE, [])
        if 0 <= idx < len(providers):
            providers.pop(idx)
            save_data(providers, API_PROVIDERS_FILE)
        await show_number_api(update, context)
        return

    if data == "api_add_new":
        context.user_data["api_add_mode"] = True
        await query.message.reply_text(
            "➕ <b>Add New Provider</b>\n\n"
            "এই ফরম্যাটে পাঠাও:\n"
            "<code>Name | API_KEY | BASE_URL</code>\n\n"
            "উদাহরণ:\n"
            "<code>Voltex | your_key_here | https://api.example.com</code>",
            parse_mode="HTML",
            reply_markup=cancel_keyboard()
        )
        return

    if data == "owner_broadcast":
        context.user_data["broadcast_mode"] = True
        await query.message.reply_text("📢 Broadcast Mode ON\nএখন যা পাঠাবে সব ইউজার পাবে।", reply_markup=cancel_keyboard())
        return

# ==================== MESSAGE HANDLER ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    uid = update.effective_user.id
    text = update.message.text.strip()

    if is_user_banned(uid) and not is_admin(uid):
        return await update.message.reply_text("🛑 YOU ARE BANNED!")

    if text in ["❌ Cancel", "Cancel"]:
        context.user_data.clear()
        return await update.message.reply_text("❌ Cancelled", reply_markup=main_keyboard(uid))

    if text == "⚙️ OWNER PANEL" and is_admin(uid):
        return await show_owner_panel(update, context)

    if context.user_data.get("api_add_mode") and is_admin(uid):
        context.user_data["api_add_mode"] = False
        parts = [p.strip() for p in text.split("|")]
        if len(parts) >= 2:
            providers = load_data(API_PROVIDERS_FILE, [])
            providers.append({
                "name": parts[0],
                "api_key": parts[1],
                "base_url": parts[2] if len(parts) > 2 else "",
                "active": True,
                "auto": False
            })
            save_data(providers, API_PROVIDERS_FILE)
            await update.message.reply_text("✅ Provider Added Successfully!", reply_markup=main_keyboard(uid))
        else:
            await update.message.reply_text("❌ Wrong format! Use: Name | API_KEY | BASE_URL")
        return

    if context.user_data.get("broadcast_mode") and is_admin(uid):
        context.user_data["broadcast_mode"] = False
        users = list(load_data(USER_DATA_FILE).keys())
        success = 0
        for u in users:
            try:
                await context.bot.send_message(int(u), f"📢 <b>ADMIN NOTICE</b>\n\n{text}", parse_mode="HTML")
                success += 1
            except:
                pass
        await update.message.reply_text(f"✅ Broadcast sent to {success} users.", reply_markup=main_keyboard(uid))
        return

    if text == "📊 TRAFFIC":
        return await leaderboard(update, context)

    if text == "🎁 Refer":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start={uid}"
        count = get_user(uid).get("referral_count", 0)
        msg = (
            f"🎁 <b>REFER & EARN</b>\n\n"
            f"🔗 YOUR LINK:\n<code>{link}</code>\n\n"
            f"👥 TOTAL REFERS: <code>{count}</code>\n"
            f"💰 PER REFER: <code>{REFERRAL_PRICE} TK</code>"
        )
        return await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard(uid))

    if text == "👤 SUPPORT":
        return await update.message.reply_text("💬 Contact Support: @YourSupportUsername", reply_markup=main_keyboard(uid))

    if text == "🔐 2FA ONLINE":
        context.user_data["mode"] = "2fa"
        return await update.message.reply_text(
            "🔐 <b>2FA ONLINE</b>\n\nSend your 2FA Secret Key:",
            parse_mode="HTML",
            reply_markup=cancel_keyboard()
        )

    if context.user_data.get("mode") == "2fa":
        context.user_data["mode"] = None
        try:
            import pyotp
            totp = pyotp.TOTP(text.replace(" ", ""))
            code = totp.now()
            await update.message.reply_text(f"✅ Your 2FA Code: <code>{code}</code>", parse_mode="HTML", reply_markup=main_keyboard(uid))
        except:
            await update.message.reply_text("❌ Invalid Secret Key!", reply_markup=main_keyboard(uid))
        return

    if not is_admin(uid):
        if not await check_force_join(context.bot, uid):
            return await show_force_join(update, context, uid)

    await update.message.reply_text("🔹 Choose an option from the menu:", reply_markup=main_keyboard(uid))

# ==================== MAIN ====================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, handle_message))

    print("🚀 BOT IS RUNNING...")
    app.run_polling()

if __name__ == "__main__":
    main()
