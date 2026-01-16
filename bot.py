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

# ================== БАЗА ДАННЫХ (POSTGRESQL) ==================
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id SERIAL PRIMARY KEY, 
            issue_code TEXT, 
            user_id BIGINT, 
            number INTEGER, 
            url TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
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

def get_available_ranges():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT number FROM links WHERE is_used = FALSE ORDER BY number")
    nums = [row['number'] for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not nums:
        return "нет доступных номеров"

    ranges = []
    if nums:
        start = nums[0]
        for i in range(1, len(nums) + 1):
            if i == len(nums) or nums[i] != nums[i-1] + 1:
                end = nums[i-1]
                ranges.append(f"{start}-{end}" if start != end else f"{start}")
                if i < len(nums): start = nums[i]
    
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
            [KeyboardButton(text="Список ссылок")], # Новая кнопка
            [KeyboardButton(text="Добавить ссылки"), KeyboardButton(text="Очистить ссылки")],
            [KeyboardButton(text="➕ Добавить ID обучающего")],
            [KeyboardButton(text="🏠 Главное меню")]
        ], resize_keyboard=True
    )

# ================== АДМИН: ОТПРАВКА СТАТИСТИКИ (ФОТО ПО КОДУ) ==================
@dp.message(F.photo, F.from_user.id.in_(ADMIN_IDS))
async def admin_quick_send_photo(message: types.Message):
    # Код должен быть в описании под фото (капшн)
    code = message.caption.strip().lower() if message.caption else None
    if not code: 
        return await message.answer("❌ Напишите код для статистики в описании к фото!")

    conn = get_db_connection()
    cur = conn.cursor()
    # Ищем в базе: либо по личному коду юзера, либо по коду конкретной выдачи
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
            await bot.send_photo(
                user['user_id'], 
                message.photo[-1].file_id,
                caption=f"✅ Статистика по коду <code>{code}</code> принята!",
                parse_mode=ParseMode.HTML
            )
            await message.answer(f"✅ Фото успешно отправлено пользователю по коду: {code}")
        except Exception:
            await message.answer("❌ Ошибка отправки (возможно, пользователь заблокировал бота)")
    else:
        await message.answer(f"❓ Код {code} не найден в базе")

# ================== ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЕЙ ==================
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    # Мы всё равно регистрируем юзера в базе (скрыто), чтобы он мог работать
    get_or_create_user(message.from_user.id, message.from_user.username)
    
    welcome_text = (
        f"🌵 <b>Привет! Это бот NEVADA TRAFFIC</b>\n\n"
        f"Я твой главный инструмент для работы с трафиком. "
        f"Здесь ты можешь получить актуальные ссылки, сдать отчет об обучении и связаться с админом.\n\n"
        f"<b>Выбери нужное действие в меню ниже:</b>"
    )
    
    await message.answer(
        welcome_text, 
        reply_markup=main_menu(), 
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def get_links_start(message: types.Message, state: FSMContext):
    available = get_available_ranges()
    if available == "нет доступных номеров":
        return await message.answer("❌ Ссылок больше нет (все выданы).")
    
    # Генерация временного кода для этой конкретной выдачи
    stat_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    await state.update_data(code=stat_code)
    
    await message.answer(
        f"✅ <b>Доступные номера:</b> {available}\n\n"
        f"Введите номер или диапазон (например: 10 или 10-15):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_nums(message: types.Message, state: FSMContext):
    text = message.text.replace(" ", "")
    try:
        if "-" in text:
            a, b = map(int, text.split("-"))
            nums = list(range(min(a, b), max(a, b) + 1))
        else:
            nums = [int(text)]
    except ValueError:
        return await message.answer("Ошибка формата. Введите число (10) или диапазон (10-20)")

    data = await state.get_data()
    issue_code = data["code"]
    conn = get_db_connection()
    cur = conn.cursor()
    
    msg = "<b>Ваши ссылки:</b>\n\n"
    found_any = False
    
    for n in nums:
        cur.execute("SELECT url FROM links WHERE number = %s AND is_used = FALSE", (n,))
        res = cur.fetchone()
        if res:
            cur.execute("UPDATE links SET is_used = TRUE WHERE number = %s", (n,))
            cur.execute("INSERT INTO issues (issue_code, user_id, number, url) VALUES (%s, %s, %s, %s)", 
                        (issue_code, message.from_user.id, n, res['url']))
            msg += f"{n}: {res['url']}\n"
            found_any = True
    
    conn.commit()
    cur.close()
    conn.close()

    if not found_any:
        await message.answer("❌ Эти номера уже выданы или не существуют.", reply_markup=main_menu())
    else:
        await message.answer(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu())
        
        # УВЕДОМЛЕНИЕ АДМИНУ (ТО, ЧТО ТЫ ПРОСИЛ)
        admin_notif = (
            f"👤 <b>Пользователь:</b> @{message.from_user.username} (ID: <code>{message.from_user.id}</code>)\n"
            f"🔢 <b>Взял номера:</b> {text}\n"
            f"🔑 <b>Код для статистики:</b> <code>{issue_code}</code>"
        )
        await bot.send_message(ADMIN_ID, admin_notif, parse_mode=ParseMode.HTML)
        
        # Сообщаем, что осталось в базе
        new_avail = get_available_ranges()
        await message.answer(f"📊 Остались свободные номера: {new_avail}")
        
    await state.clear()

@dp.message(F.text == "Я обучил человека")
async def report_start(message: types.Message, state: FSMContext):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM trainers WHERE trainer_id = %s", (str(message.from_user.id),))
    trainer = cur.fetchone()
    cur.close()
    conn.close()
    
    if not trainer and message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ У вас нет прав доступа.")
        
    await message.answer("Напишите @username обученного пользователя:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ReportState.waiting_for_username)

@dp.message(ReportState.waiting_for_username)
async def report_finish(message: types.Message, state: FSMContext):
    if not message.text.startswith("@"): 
        return await message.answer("❌ Ошибка! Формат должен быть: @username")
        
    await bot.send_message(ADMIN_ID, f"🔥 <b>НОВОЕ ОБУЧЕНИЕ</b>\nОт: @{message.from_user.username}\nОбучил: {message.text}", parse_mode=ParseMode.HTML)
    await message.answer("✅ Отчет принят", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "Создать обращение")
async def support_msg(message: types.Message):
    await message.answer("Просто напишите ваше сообщение боту, и администратор его получит.")

@dp.message(F.chat.type == "private", ~F.from_user.id.in_(ADMIN_IDS))
async def forward_to_admin(message: types.Message):
    if message.text and not message.text.startswith("/"):
        await bot.send_message(ADMIN_ID, f"💬 <b>ВОПРОС</b> от @{message.from_user.username}:\n\n{message.text}", parse_mode=ParseMode.HTML)

# ================== АДМИН-ПАНЕЛЬ ==================
@dp.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: types.Message):
    await message.answer("🔧 Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "Добавить ссылки", F.from_user.id.in_(ADMIN_IDS))
async def add_links_st(message: types.Message, state: FSMContext):
    await message.answer("Пришлите список ссылок в формате:\n№10: https://link\n№11: https://link")
    await state.set_state(AdminState.waiting_for_links)

@dp.message(F.text == "Список ссылок", F.from_user.id.in_(ADMIN_IDS))
async def admin_view_links(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor()
    # Получаем все ссылки, сортируем по номеру
    cur.execute("SELECT number, url, is_used FROM links ORDER BY number")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return await message.answer("📭 В базе пока нет ссылок.")

    response = "📊 <b>Статус всех ссылок:</b>\n\n"
    
    for row in rows:
        status = "🔴 ЗАЙНЯТА" if row['is_used'] else "🟢 СВОБОДНА"
        # Формируем строку: №10 | СВОБОДНА | ссылка
        line = f"№{row['number']} | {status}\n🔗 {row['url']}\n\n"
        
        # Проверка на длину сообщения (у Телеграм лимит 4096 символов)
        if len(response + line) > 4000:
            await message.answer(response, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            response = ""
        response += line

    if response:
        await message.answer(response, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@dp.message(AdminState.waiting_for_links)
async def save_links(message: types.Message, state: FSMContext):
    found = re.findall(r'№(\d+):\s*(http\S+)', message.text)
    conn = get_db_connection()
    cur = conn.cursor()
    count = 0
    for n, l in found:
        cur.execute("""
            INSERT INTO links (number, url, is_used) VALUES (%s, %s, FALSE) 
            ON CONFLICT (number) DO UPDATE SET url = EXCLUDED.url, is_used = FALSE
        """, (int(n), l))
        count += 1
    conn.commit()
    cur.close()
    conn.close()
    await message.answer(f"✅ Добавлено/Обновлено: {count} ссылок", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "Очистить ссылки", F.from_user.id.in_(ADMIN_IDS))
async def clear_links(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM links")
    conn.commit()
    cur.close()
    conn.close()
    await message.answer("🗑 Все ссылки удалены из базы данных.", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить ID обучающего", F.from_user.id.in_(ADMIN_IDS))
async def add_trainer(message: types.Message, state: FSMContext):
    await message.answer("Введите Telegram ID пользователя:")
    await state.set_state(AdminAddTrainerState.waiting_for_id)

@dp.message(AdminAddTrainerState.waiting_for_id)
async def save_trainer(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO trainers (trainer_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.text,))
        conn.commit()
        cur.close()
        conn.close()
        await message.answer("✅ Пользователь добавлен в список обучающих", reply_markup=admin_menu())
        await state.clear()
    else:
        await message.answer("❌ ID должен состоять только из цифр.")

@dp.message(F.text == "🏠 Главное меню")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вернулись в главное меню:", reply_markup=main_menu())

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
