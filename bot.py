import asyncio
import logging
import os
import random
import string
import json
import re
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
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
USERS_REGISTRY = "users_registry.json"

# ================== JSON ==================

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_allowed_trainers():
    data = load_json(ALLOWED_TRAINERS_FILE)
    if not data:
        data = [str(ADMIN_ID), "7869425813"]
        save_json(ALLOWED_TRAINERS_FILE, data)
    return data

def get_or_create_user_code(user_id, username):
    registry = load_json(USERS_REGISTRY)
    for code, data in registry.items():
        if data.get('id') == user_id:
            return code
    new_code = ''.join(random.choice(string.ascii_lowercase) for _ in range(6))
    registry[new_code] = {"id": user_id, "username": username}
    save_json(USERS_REGISTRY, registry)
    return new_code

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
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )

# ================== START & GO ==================

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    user_code = get_or_create_user_code(message.from_user.id, message.from_user.username)
    
    # Используем HTML, чтобы не было ошибки "can't parse entities"
    username = message.from_user.username or "NoUsername"
    admin_text = (
        f"👤 Юзер: @{username} (ID: <code>{message.from_user.id}</code>)\n"
        f"🔑 Код: <code>{user_code}</code>\n\n"
        f"⚠️ <b>ВНИМАНИЕ ЭТО ДЛЯ СМС НЕ ДЛЯ СТАТЫ</b>"
    )
    
    await bot.send_message(ADMIN_ID, admin_text, parse_mode=ParseMode.HTML)
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.message(Command("go"), F.from_user.id == ADMIN_ID)
async def admin_send_message(message: types.Message, command: CommandObject):
    if not command.args: return
    args = command.args.split(maxsplit=1)
    if len(args) < 2: return
    
    target_code, text_to_send = args[0].lower(), args[1]
    registry = load_json(USERS_REGISTRY)
    
    if target_code in registry:
        try:
            await bot.send_message(registry[target_code]['id'], text_to_send)
            await message.answer(f"✅ Отправлено коду {target_code}")
        except:
            await message.answer("❌ Ошибка отправки")

# ================== ОСТАЛЬНОЙ ФУНКЦИОНАЛ (БЕЗ ИЗМЕНЕНИЙ) ==================

@dp.message(F.text == "🏠 Главное меню")
async def back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_cmd(message: types.Message):
    await message.answer("Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def get_links(message: types.Message, state: FSMContext):
    links_db = load_json(LINKS_FILE)
    if not links_db: return await message.answer("❌ Ссылок нет")
    
    stat_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    await state.update_data(code=stat_code)
    await message.answer("Введите номер или диапазон (например: 10 или 10-15)", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_nums(message: types.Message, state: FSMContext):
    text = message.text.replace(" ", "")
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    try:
        if "-" in text:
            a, b = map(int, text.split("-"))
            nums = [str(i) for i in range(min(a,b), max(a,b)+1)]
        else:
            nums = [text]
    except: return await message.answer("Ошибка формата")

    data = await state.get_data()
    issue_code = data["code"]
    msg = "<b>Ваши ссылки:</b>\n\n"
    
    for i, n in enumerate(nums):
        if n in links_db:
            user_db[f"{issue_code}_{i}"] = {"user_id": message.from_user.id, "num": n, "username": message.from_user.username, "link": links_db[n]}
            msg += f"{n}: {links_db[n]}\n"
    
    save_json(DB_FILE, user_db)
    await message.answer(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu())
    # Твоя статистика (по-прежнему работает)
    await bot.send_message(ADMIN_ID, f"✅ Выдача @{message.from_user.username}\nНомера: {', '.join(nums)}\nКод для статьи: {issue_code}")
    await state.clear()

@dp.message(F.text == "Я обучил человека")
async def report_start(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in load_allowed_trainers():
        return await message.answer("❌ Нет доступа")
    await message.answer("Напиши @username обученного:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ReportState.waiting_for_username)

@dp.message(ReportState.waiting_for_username)
async def report_finish(message: types.Message, state: FSMContext):
    if not message.text.startswith("@"): return await message.answer("❌ Формат: @username")
    await bot.send_message(ADMIN_ID, f"🔥 ОБУЧЕНИЕ\nОт: @{message.from_user.username}\nОбучил: {message.text}")
    await message.answer("✅ Принято", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "Добавить ссылки", F.from_user.id == ADMIN_ID)
async def add_links_st(message: types.Message, state: FSMContext):
    await message.answer("Формат: №10: https://...")
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def save_links_act(message: types.Message, state: FSMContext):
    links = load_json(LINKS_FILE)
    found = re.findall(r'№(\d+):\s*(http\S+)', message.text)
    for n, l in found: links[n] = l
    save_json(LINKS_FILE, links)
    await message.answer(f"✅ Добавлено: {len(found)}", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_data(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {})
    await message.answer("🚮 Очищено")

@dp.message(F.text == "➕ Добавить ID обучающего", F.from_user.id == ADMIN_ID)
async def add_trainer_id(message: types.Message, state: FSMContext):
    await message.answer("Введи ID:")
    await state.set_state(AdminAddTrainerState.waiting_for_id)

@dp.message(AdminAddTrainerState.waiting_for_id)
async def save_trainer(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        ids = load_allowed_trainers()
        ids.append(message.text)
        save_json(ALLOWED_TRAINERS_FILE, list(set(ids)))
        await message.answer("✅ ID добавлен", reply_markup=admin_menu())
        await state.clear()

@dp.message(F.text == "Создать обращение")
async def support_msg(message: types.Message):
    await message.answer("Напиши сообщение:")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID)
async def forward_to_admin(message: types.Message):
    await bot.send_message(ADMIN_ID, f"💬 ВОПРОС от @{message.from_user.username}:\n\n{message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
