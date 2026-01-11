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
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ================== НАЛАШТУВАННЯ ==================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_IDS").split(",")]
ADMIN_ID = ADMIN_IDS[0]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================== POSTGRESQL ==================
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, user_code TEXT UNIQUE)")
    cur.execute("CREATE TABLE IF NOT EXISTS links (number TEXT PRIMARY KEY, url TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS trainers (trainer_id TEXT PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS issues (id SERIAL PRIMARY KEY, issue_code TEXT, user_id BIGINT, number TEXT, url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    cur.close()
    conn.close()

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def get_or_create_user(user_id, username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_code FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    if row:
        code = row['user_code']
    else:
        code = ''.join(random.choice(string.ascii_lowercase) for _ in range(6))
        cur.execute("INSERT INTO users (user_id, username, user_code) VALUES (%s, %s, %s)", (user_id, username, code))
        conn.commit()
    cur.close()
    conn.close()
    return code

# ================== СТАНИ (FSM) ==================
class RegState(StatesGroup):
    waiting_for_num = State()

class AdminState(StatesGroup):
    waiting_for_links = State()

class ReportState(StatesGroup):
    waiting_for_username = State()

class AdminAddTrainerState(StatesGroup):
    waiting_for_id = State()

# ================== КЛАВІАТУРИ ==================
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="ПОЛУЧИТЬ ССЫЛКИ")],
            [KeyboardButton(text="Я обучил человека")],
            [KeyboardButton(text="Создать обращение")]
        ], resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить ссылки"), KeyboardButton(text="Очистить ссылки")],
            [KeyboardButton(text="➕ Добавить ID обучающего")],
            [KeyboardButton(text="🏠 Главное меню")]
        ], resize_keyboard=True
    )

# ================== ЛОГІКА АДМІНА (ФОТО + КОД) ==================

@dp.message(F.photo, F.from_user.id.in_(ADMIN_IDS))
async def admin_quick_send_photo(message: types.Message):
    # Те, що ти просив: просто код у підписі до фото
    code = message.caption.strip().lower() if message.caption else None
    if not code: return

    conn = get_db_connection()
    cur = conn.cursor()
    # Шукаємо юзера за його кодом АБО за кодом статy (видачі)
    cur.execute("""
        SELECT user_id FROM users WHERE user_code = %s 
        UNION 
        SELECT user_id FROM issues WHERE issue_code = %s 
        LIMIT 1
    """, (code, code))
    
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user:
        try:
            await bot.send_photo(user['user_id'], message.photo[-1].file_id)
            await message.answer(f"✅ Фото відправлено коду: {code}")
        except:
            await message.answer("❌ Помилка відправки")
    else:
        await message.answer(f"❓ Код {code} не знайдено")

# ================== ХЕНДЛЕРИ КОРИСТУВАЧІВ ==================

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    user_code = get_or_create_user(message.from_user.id, message.from_user.username)
    
    username = message.from_user.username or "NoUsername"
    admin_text = (
        f"👤 Юзер: @{username} (ID: <code>{message.from_user.id}</code>)\n"
        f"🔑 Код: <code>{user_code}</code>\n\n"
        f"⚠️ <b>ВНИМАНИЕ ЭТО ДЛЯ СМС НЕ ДЛЯ СТАТЫ</b>"
    )
    await bot.send_message(ADMIN_ID, admin_text, parse_mode=ParseMode.HTML)
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def get_links(message: types.Message, state: FSMContext):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM links")
    if cur.fetchone()['count'] == 0:
        return await message.answer("❌ Ссылок нет")
    
    stat_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    await state.update_data(code=stat_code)
    await message.answer("Введите номер или диапазон (например: 10 или 10-15)", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_nums(message: types.Message, state: FSMContext):
    text = message.text.replace(" ", "")
    try:
        if "-" in text:
            a, b = map(int, text.split("-")); nums = [str(i) for i in range(min(a,b), max(a,b)+1)]
        else: nums = [text]
    except: return await message.answer("Ошибка формата")

    data = await state.get_data(); issue_code = data["code"]
    conn = get_db_connection(); cur = conn.cursor()
    msg = "<b>Ваши ссылки:</b>\n\n"; found = False
    
    for n in nums:
        cur.execute("SELECT url FROM links WHERE number = %s", (n,))
        res = cur.fetchone()
        if res:
            cur.execute("INSERT INTO issues (issue_code, user_id, number, url) VALUES (%s, %s, %s, %s)", (issue_code, message.from_user.id, n, res['url']))
            msg += f"{n}: {res['url']}\n"; found = True
    
    conn.commit(); cur.close(); conn.close()
    if not found: await message.answer("❌ Номера не найдены", reply_markup=main_menu())
    else:
        await message.answer(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu())
        await bot.send_message(ADMIN_ID, f"✅ Выдача @{message.from_user.username}\nНомера: {', '.join(nums)}\n🔑 Код для статы: {issue_code}")
    await state.clear()

# ================== ІНШІ ФУНКЦІЇ ==================

@dp.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: types.Message):
    await message.answer("Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "Добавить ссылки", F.from_user.id.in_(ADMIN_IDS))
async def add_links_st(message: types.Message, state: FSMContext):
    await message.answer("Формат: №10: https://...")
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links)
async def save_links(message: types.Message, state: FSMContext):
    found = re.findall(r'№(\d+):\s*(http\S+)', message.text)
    conn = get_db_connection(); cur = conn.cursor()
    for n, l in found:
        cur.execute("INSERT INTO links (number, url) VALUES (%s, %s) ON CONFLICT (number) DO UPDATE SET url = EXCLUDED.url", (n, l))
    conn.commit(); cur.close(); conn.close()
    await message.answer(f"✅ Добавлено: {len(found)}", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "🏠 Главное меню")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("Меню:", reply_markup=main_menu())

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
