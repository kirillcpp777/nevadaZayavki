import asyncio
import logging
import os
import random
import string
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ================== НАСТРОЙКИ ==================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_IDS").split(",")]
ADMIN_ID = ADMIN_IDS[0]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================== DB ==================
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, user_code TEXT UNIQUE)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            number INTEGER PRIMARY KEY,
            url TEXT,
            is_used BOOLEAN DEFAULT FALSE
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS trainers (trainer_id TEXT PRIMARY KEY)")
    conn.commit()
    cur.close()
    conn.close()

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def get_or_create_user(user_id, username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_code FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    if row:
        code = row["user_code"]
    else:
        code = ''.join(random.choice(string.ascii_lowercase) for _ in range(6))
        cur.execute(
            "INSERT INTO users (user_id, username, user_code) VALUES (%s,%s,%s)",
            (user_id, username, code)
        )
        conn.commit()
    cur.close()
    conn.close()
    return code

# ================== FSM ==================
class PayoutState(StatesGroup):
    confirm = State()
    screenshots = State()
    numbers = State()
    amount = State()
    pay_type = State()
    card = State()

# ================== КНОПКИ ==================
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="ПОЛУЧИТЬ ССЫЛКИ")],
            [KeyboardButton(text="ПОДАТЬ НА ВЫПЛАТУ")],
            [KeyboardButton(text="Я обучил человека")],
            [KeyboardButton(text="Создать обращение")]
        ],
        resize_keyboard=True
    )

# ================== START ==================
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    code = get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(f"Привет! Твой код: <b>{code}</b>", parse_mode=ParseMode.HTML, reply_markup=main_menu())

# ================== ВЫПЛАТА ==================
@dp.message(F.text == "ПОДАТЬ НА ВЫПЛАТУ")
async def payout_start(message: types.Message, state: FSMContext):
    await message.answer(
        "💸 <b>ПОДАЧА НА ВЫПЛАТУ</b>\n\n"
        "Бот задаст несколько вопросов.\n"
        "Нажми <b>ПОДАТЬ</b>, чтобы продолжить.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="ПОДАТЬ")]],
            resize_keyboard=True
        )
    )
    await state.set_state(PayoutState.confirm)

@dp.message(PayoutState.confirm, F.text == "ПОДАТЬ")
async def payout_confirm(message: types.Message, state: FSMContext):
    await message.answer(
        "📎 Прикрепи:\n"
        "• скрин статистики\n"
        "• скрин что ты нумеровался\n\n"
        "Отправь фото, потом напиши <b>ГОТОВО</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(PayoutState.screenshots)

@dp.message(PayoutState.screenshots, F.photo)
async def payout_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer("📸 Принято. Можешь отправить ещё или напиши <b>ГОТОВО</b>", parse_mode=ParseMode.HTML)

@dp.message(PayoutState.screenshots, F.text == "ГОТОВО")
async def payout_done_photos(message: types.Message, state: FSMContext):
    await message.answer("🔢 Укажи номер или диапазон (пример: 10 или 10-20)")
    await state.set_state(PayoutState.numbers)

@dp.message(PayoutState.numbers)
async def payout_numbers(message: types.Message, state: FSMContext):
    await state.update_data(numbers=message.text)
    await message.answer("💰 Сколько залили?")
    await state.set_state(PayoutState.amount)

@dp.message(PayoutState.amount)
async def payout_amount(message: types.Message, state: FSMContext):
    await state.update_data(amount=message.text)
    await message.answer(
        "💳 Выбери способ выплаты:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="УКР КАРТА")],
                [KeyboardButton(text="КБ")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(PayoutState.pay_type)

@dp.message(PayoutState.pay_type)
async def payout_pay_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pay_type = message.text
    await state.update_data(pay_type=pay_type)

    # ЕСЛИ КБ — СРАЗУ ОТПРАВЛЯЕМ АДМИНУ
    if pay_type == "КБ":
        text = (
            "💸 <b>ЗАЯВКА НА ВЫПЛАТУ</b>\n\n"
            f"👤 @{message.from_user.username}\n"
            f"🔢 Номера: {data.get('numbers')}\n"
            f"💰 Залили: {data.get('amount')}\n"
            f"💳 Способ: КБ"
        )

        await bot.send_message(ADMIN_ID, text, parse_mode=ParseMode.HTML)
        for p in data.get("photos", []):
            await bot.send_photo(ADMIN_ID, p)

        await message.answer("✅ Заявка отправлена", reply_markup=main_menu())
        await state.clear()
    else:
        await message.answer("✍️ Введи номер карты:")
        await state.set_state(PayoutState.card)

@dp.message(PayoutState.card)
async def payout_card(message: types.Message, state: FSMContext):
    data = await state.get_data()

    text = (
        "💸 <b>ЗАЯВКА НА ВЫПЛАТУ</b>\n\n"
        f"👤 @{message.from_user.username}\n"
        f"🔢 Номера: {data.get('numbers')}\n"
        f"💰 Залили: {data.get('amount')}\n"
        f"💳 Способ: УКР КАРТА\n"
        f"💳 Карта: {message.text}"
    )

    await bot.send_message(ADMIN_ID, text, parse_mode=ParseMode.HTML)
    for p in data.get("photos", []):
        await bot.send_photo(ADMIN_ID, p)

    await message.answer("✅ Заявка отправлена", reply_markup=main_menu())
    await state.clear()

# ================== RUN ==================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
