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
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0]) 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Храним данные: { "код": {"user_id": 123, "num": "5"} }
DB_FILE = "data_storage.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db_data):
    with open(DB_FILE, "w") as f:
        json.dump(db_data, f)

db = load_db()

class RegState(StatesGroup):
    waiting_for_num = State()

def generate_code(length=5):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- Клавиатуры ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆘 Создать обращение")],
            [KeyboardButton(text="🔗 ПОЛУЧИТЬ ССЫЛКИ")]
        ],
        resize_keyboard=True
    )

# --- Обработчики ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Воспользуйся меню ниже:", reply_markup=main_menu())

@dp.message(F.text == "🔗 ПОЛУЧИТЬ ССЫЛКИ")
async def start_reg(message: types.Message, state: FSMContext):
    # Генерируем код сразу
    unique_code = generate_code()
    
    # Считаем свободные номера (1-100)
    taken_nums = [str(item['num']) for item in db.values()]
    free_nums = [str(i) for i in range(1, 101) if str(i) not in taken_nums]
    available_str = ", ".join(free_nums[:15]) # Показываем первые 15
    
    await message.answer(
        f"Это для тех, кто будет лить, но еще не в команде.\n\n"
        f"Твой уникальный код: <code>{unique_code}</code>\n"
        f"Теперь <b>пронумеруйся</b> (свободные номера: {available_str}...)\n"
        f"Введи номер в чат:",
        parse_mode=ParseMode.HTML,
        reply_markup=types.ReplyKeyboardRemove()
    )
    # Сохраняем код в FSM, чтобы привязать к нему номер на следующем шаге
    await state.update_data(temp_code=unique_code)
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_num(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введи только число!")

    num = message.text.strip()
    taken_nums = [str(item['num']) for item in db.values()]
    
    if num in taken_nums:
        return await message.answer(f"Номер {num} уже занят, выбери другой!")

    data = await state.get_data()
    code = data['temp_code']

    # Сохраняем всё в базу
    db[code] = {
        "user_id": message.from_user.id,
        "num": num,
        "username": message.from_user.username
    }
    save_db(db)

    await message.answer("Отлично! Ты пронумеровался! Жди статистику!", reply_markup=main_menu())
    await state.clear()

    # Уведомляем админа
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Юзер пронумеровался!</b>\n"
        f"👤 Юзер: @{message.from_user.username}\n"
        f"🔢 Выбранный номер: <b>{num}</b>\n"
        f"🔑 Код для статы: <code>{code}</code>",
        parse_mode=ParseMode.HTML
    )

# --- Отправка ФОТО-статистики админом ---
@dp.message(F.from_user.id == ADMIN_ID, F.photo)
async def admin_send_photo(message: types.Message):
    if not message.caption:
        return

    target_code = message.caption.strip().lower()
    
    if target_code in db:
        user_id = db[target_code]['user_id']
        try:
            await bot.send_photo(
                user_id, 
                message.photo[-1].file_id, 
                caption=f"📊 Статистика по коду: <code>{target_code}</code>",
                parse_mode=ParseMode.HTML
            )
            await message.answer(f"✅ Стата для кода <code>{target_code}</code> отправлена.")
        except Exception as e:
            await message.answer(f"Ошибка: {e}")

# --- Поддержка (Reply) ---
@dp.message(F.text == "🆘 Создать обращение")
async def start_support(message: types.Message):
    await message.answer("Напиши свой вопрос админу ниже 👇")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, ~F.text.in_(["🔗 ПОЛУЧИТЬ ССЫЛКИ", "🆘 Создать обращение"]))
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
        await bot.send_message(user_id, f"<b>👨‍💻 ОТВЕТ АДМИНА:</b>\n\n{message.text or ''}", parse_mode=ParseMode.HTML)
        await message.answer("Отправлено.")
    except:
        pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
