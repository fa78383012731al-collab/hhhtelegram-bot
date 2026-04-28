import os
import logging
import json
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from flask import Flask
import asyncio
from threading import Thread
from drive_service import GoogleDriveService

# إعداد السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# الثوابت
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATA_FILE = "user_projects.json"
TEMP_DIR = "/tmp/bot_uploads"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# حالات المحادثة
CHOOSE_ACTION, PROJECT_TYPE, MAIN_NAME, SUB_NAME, UPLOAD, OLD_PROJECT = range(6)

ADAA_ITEMS = [
    "أداء الواجبات الوظيفية", "التفاعل مع المجتمع المهني", "التفاعل مع أولياء الأمور",
    "التنويع في استراتيجيات التدريس", "تحسين نتائج المتعلمين", "إعداد وتنفيذ خطة التعلم",
    "توظيف تقنيات ووسائل التعلم", "تهيئة البيئة التعليمية", "الإدارة الصفية",
    "تحليل نتائج المتعلمين وتشخيص مستوياتهم", "تنويع أساليب التقويم"
]

# خادم ويب لـ Render
app = Flask(__name__)
@app.route('/')
def health(): return "OK", 200

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# إدارة البيانات
def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_db(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

db = load_db()
drive = GoogleDriveService()
sessions = {}

# --- الـ Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['➕ مشروع جديد', '📂 مشاريعي السابقة']]
    await update.message.reply_text(
        "مرحباً بك في النسخة الاحترافية من بوت الشواهد! 🚀\nتم بناء هذه النسخة لتعمل باستقرار 24/7.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_ACTION

async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    user_id = str(update.effective_user.id)
    if choice == '➕ مشروع جديد':
        await update.message.reply_text("اختر نوع المشروع:", reply_markup=ReplyKeyboardMarkup([['ملف أداء وظيفي', 'ملف إنجاز']], resize_keyboard=True))
        return PROJECT_TYPE
    elif choice == '📂 مشاريعي السابقة':
        if user_id not in db or not db[user_id]:
            await update.message.reply_text("لا توجد مشاريع.")
            return CHOOSE_ACTION
        keyboard = [[n] for n in db[user_id].keys()] + [['⬅️ عودة']]
        await update.message.reply_text("اختر المشروع:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return OLD_PROJECT
    return CHOOSE_ACTION

async def set_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    sessions[user_id] = {"type": update.message.text, "subs": {}}
    await update.message.reply_text("أرسل اسم صاحب المشروع:")
    return MAIN_NAME

async def create_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    user_id = str(update.effective_user.id)
    msg = await update.message.reply_text("⏳ جاري تهيئة المجلدات في Google Drive...")
    
    folder = await drive.create_folder(name)
    sessions[user_id].update({"name": name, "id": folder['id'], "link": folder['webViewLink']})
    
    if sessions[user_id]["type"] == 'ملف أداء وظيفي':
        for item in ADAA_ITEMS:
            sub = await drive.create_folder(item, folder['id'])
            sessions[user_id]["subs"][item] = {"id": sub['id'], "link": sub['webViewLink']}
        
        if user_id not in db: db[user_id] = {}
        db[user_id][name] = sessions[user_id]
        save_db(db)
        return await show_menu(update, context)
    else:
        await msg.edit_text("أرسل اسم المجلد الفرعي الأول:")
        return SUB_NAME

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    session = sessions[user_id]
    keyboard = []
    items = list(session["subs"].keys())
    for i in range(0, len(items), 2): keyboard.append(items[i:i+2])
    if session["type"] != 'ملف أداء وظيفي': keyboard.append(["➕ إضافة بند"])
    keyboard.append(["🔗 الروابط", "🏠 الرئيسية"])
    await update.message.reply_text(f"📍 المشروع: {session['name']}", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return UPLOAD

async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    session = sessions.get(user_id)
    if not session: return await start(update, context)
    
    if text == "🏠 الرئيسية": return await start(update, context)
    if text == "🔗 الروابط":
        links = "\n".join([f"🔸 {n}:\n{d['link']}" for n, d in session["subs"].items()])
        await update.message.reply_text(f"🔗 الروابط:\n\n{links}")
        return UPLOAD
    if text == "➕ إضافة بند":
        await update.message.reply_text("أرسل اسم البند:")
        return SUB_NAME
    if text in session["subs"]:
        session["active"] = text
        await update.message.reply_text(f"📍 تم تحديد: {text}\nأرسل الملفات الآن.")
        return UPLOAD

    # الرفع
    file_info = None
    if update.message.document: file_info = (await update.message.document.get_file(), update.message.document.file_name, False)
    elif update.message.photo: file_info = (await update.message.photo[-1].get_file(), f"img_{update.message.message_id}.jpg", True)
    elif update.message.video: file_info = (await update.message.video.get_file(), update.message.video.file_name or "video.mp4", False)

    if file_info and "active" in session:
        file_obj, name, is_img = file_info
        status = await update.message.reply_text(f"⏳ جاري رفع {name}...")
        path = os.path.join(TEMP_DIR, name)
        await file_obj.download_to_drive(path)
        
        if is_img:
            with Image.open(path) as img:
                if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                img.save(path, "JPEG", quality=70, optimize=True)

        try:
            await drive.upload_file(path, name, session["subs"][session["active"]]["id"])
            await status.edit_text(f"✅ تم رفع {name}")
        except Exception as e: await status.edit_text(f"❌ خطأ: {e}")
        finally:
            if os.path.exists(path): os.remove(path)
    return UPLOAD

async def add_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    user_id = str(update.effective_user.id)
    session = sessions[user_id]
    sub = await drive.create_folder(name, session["id"])
    session["subs"][name] = {"id": sub['id'], "link": sub['webViewLink']}
    db[user_id][session["name"]] = session
    save_db(db)
    return await show_menu(update, context)

async def load_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    user_id = str(update.effective_user.id)
    if name == '⬅️ عودة': return await start(update, context)
    if name in db.get(user_id, {}):
        sessions[user_id] = db[user_id][name]
        return await show_menu(update, context)
    return CHOOSE_ACTION

if __name__ == '__main__':
    Thread(target=run_web, daemon=True).start()
    if TOKEN:
        bot = ApplicationBuilder().token(TOKEN).build()
        bot.add_handler(ConversationHandler(
            entry_points=[CommandHandler('start', start), MessageHandler(filters.Regex('^🏠 الرئيسية$'), start)],
            states={
                CHOOSE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_action)],
                PROJECT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_type)],
                MAIN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_main)],
                SUB_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sub)],
                UPLOAD: [MessageHandler(filters.ALL & ~filters.COMMAND, handle_upload)],
                OLD_PROJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, load_old)],
            },
            fallbacks=[CommandHandler('start', start)],
            allow_reentry=True
        ))
        bot.run_polling()
