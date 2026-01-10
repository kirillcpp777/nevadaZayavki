import asyncio
import logging
import os
import random
import string
import json
import re
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
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0])

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "data_storage.json"
LINKS_FILE = "links.json"
ALLOWED_TRAINERS_FILE = "allowed_trainers.json"

# ================== JSON ==================

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_allowed_trainers():
    data = load_json(ALLOWED_TRAINERS_FILE)
    if not data:
        data = ["7869425813"]
        save_json(ALLOWED_TRAINERS_FILE, data)
    return data

# ================== FSM ==================

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
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить ссылки"), KeyboardButton(text="Очистить ссылки")],
            [KeyboardButton(text="➕ Добавить ID обучающего")],
            [KeyboardButton(text="Рассылка по ID (инфо)")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )

# ================== START ==================

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.message(F.text == "🏠 Главное меню")
async def back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())

# ================== ССЫЛКИ ==================

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def get_links(message: types.Message, state: FSMContext):
    links_db = load_json(LINKS_FILE)
    if not links_db:
        return await message.answer("❌ Ссылок нет")

    user_db = load_json(DB_FILE)
    taken = [str(v["num"]) for v in user_db.values()]
    free = [k for k in links_db.keys() if k not in taken]

    if not free:
        return await message.answer("❌ Все номера заняты")

    code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    await state.update_data(code=code)

    await message.answer(
        "Введите номер или диапазон (пример: 10 или 10-15)",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_nums(message: types.Message, state: FSMContext):
    text = message.text.replace(" ", "")
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)

    nums = []
    if "-" in text:
        a, b = map(int, text.split("-"))
        nums = [str(i) for i in range(min(a,b), max(a,b)+1)]
    else:
        nums = [text]

    for n in nums:
        if n not in links_db:
            return await message.answer(f"❌ Номер {n} не существует")

    data = await state.get_data()
    code = data["code"]

    msg = "<b>Ваши ссылки:</b>\n\n"
    for i, n in enumerate(nums):
        user_db[f"{code}_{i}"] = {
            "user_id": message.from_user.id,
            "num": n,
            "username": message.from_user.username,
            "link": links_db[n]
        }
        msg += f"{n}: {links_db[n]}\n"

    save_json(DB_FILE, user_db)

    await message.answer(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu())
    await bot.send_message(
        ADMIN_ID,
        f"✅ Выдача @{message.from_user.username}\nНомера: {', '.join(nums)}\nКод: {code}"
    )
    await state.clear()

# ================== ОБУЧЕНИЕ ==================

@dp.message(F.text == "Я обучил человека")
async def report_start(message: types.Message, state: FSMContext):
    allowed = load_allowed_trainers()
    if str(message.from_user.id) not in allowed:
        return await message.answer("❌ У тебя нет доступа")

    await message.answer(
        "Напиши @username обученного\nПример: @dsaads",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(ReportState.waiting_for_username)

@dp.message(ReportState.waiting_for_username)
async def report_finish(message: types.Message, state: FSMContext):
    if not re.match(r'^@[\w\d_]{3,}$', message.text):
        return await message.answer("❌ Неверный формат")

    await bot.send_message(
        ADMIN_ID,
        f"🔥 ОБУЧЕНИЕ\n"
        f"От: @{message.from_user.username}\n"
        f"ID: {message.from_user.id}\n"
        f"Обучил: {message.text}"
    )

    await message.answer("✅ Принято", reply_markup=main_menu())
    await state.clear()

# ================== АДМИНКА ==================

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin(message: types.Message):
    await message.answer("Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить ID обучающего", F.from_user.id == ADMIN_ID)
async def add_trainer_start(message: types.Message, state: FSMContext):
    await message.answer("Введи ID:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AdminAddTrainerState.waiting_for_id)

@dp.message(AdminAddTrainerState.waiting_for_id, F.from_user.id == ADMIN_ID)
async def add_trainer_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Только цифры")

    ids = load_allowed_trainers()
    if message.text in ids:
        return await message.answer("⚠️ Уже есть")

    ids.append(message.text)
    save_json(ALLOWED_TRAINERS_FILE, ids)

    await message.answer("✅ ID добавлен", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "Добавить ссылки", F.from_user.id == ADMIN_ID)
async def add_links(message: types.Message, state: FSMContext):
    await message.answer("Формат: №10: https://...")
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def save_links(message: types.Message, state: FSMContext):
    lines = message.text.split("\n")
    links = load_json(LINKS_FILE)
    count = 0

    for l in lines:
        m = re.search(r'№(\d+):\s*(http\S+)', l)
        if m:
            links[m.group(1)] = m.group(2)
            count += 1

    save_json(LINKS_FILE, links)
    await message.answer(f"Добавлено: {count}", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {})
    await message.answer("Очищено")

# ================== SUPPORT ==================

@dp.message(F.text == "Создать обращение")
async def support(message: types.Message):
    await message.answer("Напиши сообщение:")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID)
async def to_admin(message: types.Message):
    await bot.send_message(
        ADMIN_ID,
        f"💬 ВОПРОС\nID: {message.from_user.id}\n@{message.from_user.username}\n\n{message.text}"
    )

# ================== RUN ==================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
