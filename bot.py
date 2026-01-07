import asyncio
import logging
import os
import random
import string
import json
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0]) 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Файл для хранения кодов, чтобы они не удалялись после перезагрузки
DB_FILE = "codes_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f)

# Загружаем базу при старте
codes_db = load_db()

def generate_code(length=5):
    characters = string.ascii_lowercase + string.digits
    while True:
        code = ''.join(random.choice(characters) for _ in range(length))
        if code not in codes_db:
            return code

# --- Клавиатуры ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆘 Создать обращение")],
            [KeyboardButton(text="🔗 ПОЛУЧИТЬ ССЫЛКУ")]
        ],
        resize_keyboard=True
    )

# --- Обработчики ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Привет, {message.from_user.first_name}!\nИспользуй меню:",
        reply_markup=main_menu()
    )

@dp.message(F.text == "🔗 ПОЛУЧИТЬ ССЫЛКУ")
async def get_link(message: types.Message):
    new_code = generate_code()
    codes_db[new_code] = message.from_user.id
    save_db(codes_db) # Сохраняем в файл
    
    await message.answer(
        f"Твой уникальный номер для статистики: <code>{new_code}</code>\n"
        "Сюда будут приходить фото-отчеты по этому номеру.",
        parse_mode=ParseMode.HTML
    )
    
    await bot.send_message(
        ADMIN_ID, 
        f"🆕 <b>Выдан код:</b> <code>{new_code}</code>\n"
        f"Юзер: @{message.from_user.username} (ID: {message.from_user.id})",
        parse_mode=ParseMode.HTML
    )

# --- Отправка ФОТО-статистики админом ---
@dp.message(F.from_user.id == ADMIN_ID, F.photo)
async def send_photo_stats(message: types.Message):
    # Проверяем, есть ли в описании к фото код
    if not message.caption:
        return # Если админ просто прислал фото без текста, ничего не делаем

    target_code = message.caption.strip().lower()
    
    if target_code in codes_db:
        user_id = codes_db[target_code]
        try:
            # Пересылаем фото юзеру
            await bot.send_photo(
                user_id, 
                message.photo[-1].file_id, 
                caption=f"📊 <b>Статистика по номеру:</b> <code>{target_code}</code>",
                parse_mode=ParseMode.HTML
            )
            await message.answer(f"✅ Фото отправлено владельцу кода <code>{target_code}</code>")
        except Exception as e:
            await message.answer(f"❌ Ошибка отправки: {e}")
    else:
        # Если это не код, возможно это ответ в техподдержку (через Reply)
        pass

# --- Поддержка (как и была) ---
@dp.message(F.text == "🆘 Создать обращение")
async def start_support(message: types.Message):
    await message.answer("Диалог открыт. Пиши свой вопрос админу 👇")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, ~F.text.in_(["🔗 ПОЛУЧИТЬ ССЫЛКУ", "🆘 Создать обращение"]))
async def forward_to_admin(message: types.Message):
    info = f"<b>💬 ВОПРОС</b>\n🆔 ID: <code>{message.from_user.id}</code>\n👤 @{message.from_user.username}\n───\n"
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=info + (message.caption or ""), parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(ADMIN_ID, info + (message.text or ""), parse_mode=ParseMode.HTML)

@dp.message(F.from_user.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption
        user_id = int(reply_text.split("ID:")[1].split("\n")[0].strip())
        
        if message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=f"<b>👨‍💻 ОТВЕТ:</b>\n{message.caption or ''}", parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(user_id, f"<b>👨‍💻 ОТВЕТ:</b>\n\n{message.text}", parse_mode=ParseMode.HTML)
        await message.answer("Отправлено.")
    except:
        pass

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
