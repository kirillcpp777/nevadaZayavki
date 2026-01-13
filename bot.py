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
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup

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

# ================== POSTGRESQL ==================
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, user_code TEXT UNIQUE)")
    # Номер теперь INT для правильной сортировки, добавлена колонка is_used
    cur.execute("CREATE TABLE IF NOT EXISTS links (number INT PRIMARY KEY, url TEXT, is_used BOOLEAN DEFAULT FALSE)")
    cur.execute("CREATE TABLE IF NOT EXISTS trainers (trainer_id TEXT PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS issues (id SERIAL PRIMARY KEY, issue_code TEXT, user_id BIGINT, number INT, url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
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

def get_free_ranges():
    """Функция для группировки свободных номеров в красивые диапазоны"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT number FROM links WHERE is_used = FALSE ORDER BY number")
    nums = [row['number'] for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not nums: return "нет свободных"

    ranges = []
    if nums:
        start = nums[0]
        for i in range(1, len(nums)):
            if nums[i] != nums[i-1] + 1:
                ranges.append(f"{start}-{nums[i-1]}" if start != nums[i-1] else f"{start}")
                start = nums[i]
        ranges.append(f"{start}-{nums[-1]}" if start != nums[-1] else f"{start}")
    return ", ".join(ranges)

# ================== СОСТОЯНИЯ (FSM) ==================
class RegState(StatesGroup):
    waiting_for_num = State()

class AdminState(StatesGroup):
    waiting_for_links = State()

class ReportState(StatesGroup):
    waiting_for_username = State()

class AdminAddTrainerState(StatesGroup):
    waiting_for_id = State()

# ================== КЛАВИАТУРЫ ==================
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
            [KeyboardButton(text="Добавить ссылки"), KeyboardButton(text="Очистить все ссылки")],
            [KeyboardButton(text="➕ Добавить ID обучающего")],
            [KeyboardButton(text="🏠 Главное меню")]
        ], resize_keyboard=True
    )

# ================== ХЕНДЛЕРЫ АДМИНА ==================

@dp.message(F.photo, F.from_user.id.in_(ADMIN_IDS))
async def admin_quick_send_photo(message: types.Message):
    code = message.caption.strip().lower() if message.caption else None
    if not code: return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_code = %s UNION SELECT user_id FROM issues WHERE issue_code = %s LIMIT 1", (code, code))
    user = cur.fetchone()
    cur.close(); conn.close()

    if user:
        try:
            await bot.send_photo(user['user_id'], message.photo[-1].file_id)
            await message.answer(f"✅ Фото отправлено коду: {code}")
        except: await message.answer("❌ Ошибка отправки")
    else: await message.answer(f"❓ Код {code} не найден")

@dp.message(F.text == "Очистить все ссылки", F.from_user.id.in_(ADMIN_IDS))
async def clear_links(message: types.Message):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM links")
    conn.commit(); cur.close(); conn.close()
    await message.answer("🗑 Все ссылки удалены из базы.")

# ================== ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЕЙ ==================

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    user_code = get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(f"Привет! Твой код: {user_code}", reply_markup=main_menu())

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def get_links_start(message: types.Message, state: FSMContext):
    free_text = get_free_ranges()
    if free_text == "нет свободных":
        return await message.answer("❌ Свободных ссылок сейчас нет.")
    
    stat_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    await state.update_data(code=stat_code)
    await message.answer(
        f"<b>Доступные номера:</b> {free_text}\n\nВведите номер или диапазон (например: 10 или 10-15):",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_nums(message: types.Message, state: FSMContext):
    text = message.text.replace(" ", "")
    try:
        if "-" in text:
            a, b = map(int, text.split("-"))
            nums = list(range(min(a,b), max(a,b)+1))
        else: nums = [int(text)]
    except: return await message.answer("Ошибка формата. Введите число или диапазон (10-15)")

    data = await state.get_data(); issue_code = data["code"]
    conn = get_db_connection(); cur = conn.cursor()
    
    msg = "<b>Ваши ссылки:</b>\n\n"; found_count = 0
    for n in nums:
        cur.execute("SELECT url FROM links WHERE number = %s AND is_used = FALSE", (n,))
        res = cur.fetchone()
        if res:
            cur.execute("UPDATE links SET is_used = TRUE WHERE number = %s", (n,))
            cur.execute("INSERT INTO issues (issue_code, user_id, number, url) VALUES (%s, %s, %s, %s)", (issue_code, message.from_user.id, n, res['url']))
            msg += f"#{n}: {res['url']}\n"; found_count += 1
    
    conn.commit(); cur.close(); conn.close()
    if found_count == 0:
        await message.answer("❌ Выбранные номера уже заняты или не существуют.", reply_markup=main_menu())
    else:
        await message.answer(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=main_menu())
        await bot.send_message(ADMIN_ID, f"✅ Выдача {found_count} шт. @{message.from_user.username}\n🔑 Код: {issue_code}")
    await state.clear()

@dp.message(F.text == "Я обучил человека")
async def report_start(message: types.Message, state: FSMContext):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM trainers WHERE trainer_id = %s", (str(message.from_user.id),))
    if not cur.fetchone() and message.from_user.id not in ADMIN_IDS:
        cur.close(); conn.close()
        return await message.answer("❌ У вас нет прав")
    cur.close(); conn.close()
    await message.answer("Напиши @username обученного:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ReportState.waiting_for_username)

@dp.message(ReportState.waiting_for_username)
async def report_finish(message: types.Message, state: FSMContext):
    if not message.text or not message.text.startswith("@"): 
        return await message.answer("❌ Формат: @username")
    await bot.send_message(ADMIN_ID, f"🔥 ОБУЧЕНИЕ\nОт: @{message.from_user.username}\nОбучил: {message.text}")
    await message.answer("✅ Принято", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "Создать обращение")
async def support_msg(message: types.Message):
    await message.answer("Просто напишите ваше сообщение следующим текстом, админ его получит.")

@dp.message(F.chat.type == "private", ~F.from_user.id.in_(ADMIN_IDS))
async def forward_to_admin(message: types.Message):
    if message.text and not message.text.startswith("/"):
        await bot.send_message(ADMIN_ID, f"💬 ВОПРОС от @{message.from_user.username}:\n\n{message.text}")

# ================== АДМИН-ПАНЕЛЬ ==================

@dp.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: types.Message):
    await message.answer("Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "Добавить ссылки", F.from_user.id.in_(ADMIN_IDS))
async def add_links_st(message: types.Message, state: FSMContext):
    await message.answer("Пришлите список. Формат:\n№10: https://link1\n№11: https://link2")
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links)
async def save_links(message: types.Message, state: FSMContext):
    found = re.findall(r'№?(\d+)[:\s]+(http\S+)', message.text)
    conn = get_db_connection(); cur = conn.cursor()
    for n, l in found:
        cur.execute("""
            INSERT INTO links (number, url, is_used) VALUES (%s, %s, FALSE) 
            ON CONFLICT (number) DO UPDATE SET url = EXCLUDED.url, is_used = FALSE
        """, (int(n), l))
    conn.commit(); cur.close(); conn.close()
    await message.answer(f"✅ Успешно добавлено/обновлено: {len(found)}", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "➕ Добавить ID обучающего", F.from_user.id.in_(ADMIN_IDS))
async def add_trainer(message: types.Message, state: FSMContext):
    await message.answer("Введи Telegram ID пользователя:")
    await state.set_state(AdminAddTrainerState.waiting_for_id)

@dp.message(AdminAddTrainerState.waiting_for_id)
async def save_trainer(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO trainers (trainer_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.text,))
        conn.commit(); cur.close(); conn.close()
        await message.answer("✅ Пользователь добавлен в список обучающих", reply_markup=admin_menu())
        await state.clear()
    else: await message.answer("❌ ID должен быть числом")

@dp.message(F.text == "🏠 Главное меню")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("Вы вернулись в меню:", reply_markup=main_menu())

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
