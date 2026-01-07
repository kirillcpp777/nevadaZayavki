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

# --- Конфигурация ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0]) 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Файл базы: { "код": user_id }
DB_FILE = "codes_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f)

codes_db = load_db()

def generate_unique_code(length=5):
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
        f"Привет, {message.from_user.first_name}!\nВоспользуйся меню ниже:",
        reply_markup=main_menu()
    )

@dp.message(F.text == "🔗 ПОЛУЧИТЬ ССЫЛКУ")
async def get_link(message: types.Message):
    # Генерируем уникальный код (например: 7vsh5)
    new_code = generate_unique_code()
    codes_db[new_code] = message.from_user.id
    save_db(codes_db)
    
    await message.answer(
        f"Это для тех, кто будет лить, но еще не присоединился в команду.\n\n"
        f"Твой уникальный номер: <code>{new_code}</code>\n\n"
        "<b>Ты успешно пронумеровался! Жди статистику!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )
    
    # Уведомление тебе (админу)
    await bot.send_message(
        ADMIN_ID, 
        f"🆕 <b>Выдан новый уникальный код!</b>\n"
        f"Код: <code>{new_code}</code>\n"
        f"Юзер: @{message.from_user.username} (ID: {message.from_user.id})",
        parse_mode=ParseMode.HTML
    )

# --- Отправка ФОТО-статистики админом ---
@dp.message(F.from_user.id == ADMIN_ID, F.photo)
async def admin_send_photo(message: types.Message):
    # Если под фото есть текст — проверяем, не код ли это
    if not message.caption:
        return

    target_code = message.caption.strip().lower()
    
    if target_code in codes_db:
        user_id = codes_db[target_code]
        try:
            await bot.send_photo(
                user_id, 
                message.photo[-1].file_id, 
                caption=f"📊 Статистика по твоему номеру: <code>{target_code}</code>",
                parse_mode=ParseMode.HTML
            )
            await message.answer(f"✅ Фото успешно отправлено владельцу кода <code>{target_code}</code>")
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке юзеру: {e}")

# --- Поддержка (Reply) ---
@dp.message(F.text == "🆘 Создать обращение")
async def start_support(message: types.Message):
    await message.answer("Напиши свой вопрос админу ниже 👇")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, ~F.text.in_(["🔗 ПОЛУЧИТЬ ССЫЛКУ", "🆘 Создать обращение"]))
async def forward_to_admin(message: types.Message):
    # Пересылка сообщения админу с ID отправителя для Reply
    info = f"<b>💬 ВОПРОС</b>\n🆔 ID: <code>{message.from_user.id}</code>\n👤 @{message.from_user.username}\n───\n"
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=info + (message.caption or ""), parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(ADMIN_ID, info + (message.text or ""), parse_mode=ParseMode.HTML)

@dp.message(F.from_user.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        # Достаем ID из текста сообщения, на которое отвечаем
        reply_text = message.reply_to_message.text or message.reply_to_message.caption
        user_id = int(reply_text.split("ID:")[1].split("\n")[0].strip())
        
        if message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=f"<b>👨‍💻 ОТВЕТ АДМИНА:</b>\n{message.caption or ''}", parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(user_id, f"<b>👨‍💻 ОТВЕТ АДМИНА:</b>\n\n{message.text}", parse_mode=ParseMode.HTML)
        await message.answer("Отправлено.")
    except Exception as e:
        await message.answer(f"Не удалось отправить ответ: {e}")

async def main():
    print("Бот запущен (Режим: Уникальные коды + Фото стата)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
