import asyncio
import logging
import os
import random
import string
import json
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
# Берем первый ID из списка администраторов
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0])

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "data_storage.json"
LINKS_FILE = "links.json"

# --- Работа с JSON ---
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except: return {}
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Состояния
class AdminState(StatesGroup):
    waiting_for_links = State()

# --- Клавиатуры ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆘 Создать обращение")],
            [KeyboardButton(text="🔗 ПОЛУЧИТЬ ССЫЛКИ")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Добавить ссылки"), KeyboardButton(text="📊 Статус ссылок")],
            [KeyboardButton(text="🧹 Очистить ссылки"), KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )

# --- ОБЩИЕ КОМАНДЫ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Добро пожаловать! Воспользуйся меню:", reply_markup=main_menu())

@dp.message(F.text == "🏠 Главное меню")
async def back_home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())

# --- ЛОГИКА ДЛЯ ЮЗЕРА ---

@dp.message(F.text == "🔗 ПОЛУЧИТЬ ССЫЛКИ")
async def show_user_links(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    # Проверка, нет ли уже ссылки у юзера
    for data in user_db.values():
        if data.get('user_id') == message.from_user.id:
            return await message.answer(
                f"Ты уже занял номер {data['num']}!\n"
                f"🔗 Ссылка: {data['link']}\n"
                f"🔑 Твой код: <code>{next(k for k, v in user_db.items() if v == data)}</code>",
                parse_mode=ParseMode.HTML
            )

    if not links_db:
        return await message.answer("Свободных ссылок пока нет.")

    taken_nums = [str(item['num']) for item in user_db.values()]
    free_nums = [n for n in links_db.keys() if n not in taken_nums]
    
    if not free_nums:
        return await message.answer("Все номера заняты!")

    builder = InlineKeyboardBuilder()
    for num in sorted(free_nums, key=lambda x: int(x) if x.isdigit() else 0):
        builder.button(text=f"№ {num}", callback_data=f"take_{num}")
    
    builder.adjust(4)
    await message.answer("Выберите свободный номер для работы:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("take_"))
async def process_take_link(callback: types.CallbackQuery):
    num = callback.data.split("_")[1]
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    taken_nums = [str(item['num']) for item in user_db.values()]
    if num in taken_nums:
        return await callback.answer("Этот номер только что заняли!", show_alert=True)

    unique_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    link = links_db[num]
    
    user_db[unique_code] = {
        "user_id": callback.from_user.id,
        "num": num,
        "username": callback.from_user.username or "NoUsername",
        "link": link
    }
    save_json(DB_FILE, user_db)

    await callback.message.edit_text(
        f"✅ <b>Номер {num} закреплен за тобой!</b>\n\n"
        f"🔗 Ссылка: {link}\n"
        f"🔑 Твой код для статистики: <code>{unique_code}</code>\n\n"
        f"Удачи в работе!",
        parse_mode=ParseMode.HTML
    )
    
    await bot.send_message(
        ADMIN_ID, 
        f"🔔 <b>Новый трафер!</b>\nЮзер: @{callback.from_user.username}\nНомер: {num}\nКод: <code>{unique_code}</code>",
        parse_mode=ParseMode.HTML
    )

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Панель управления:", reply_markup=admin_menu())

@dp.message(F.text == "📊 Статус ссылок", F.from_user.id == ADMIN_ID)
async def admin_status(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    if not links_db:
        return await message.answer("База ссылок пуста.")

    taken_nums = {item['num']: item['username'] for item in user_db.values()}
    builder = InlineKeyboardBuilder()

    for num in sorted(links_db.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        status = "❌" if num in taken_nums else "✅"
        builder.button(text=f"{status} №{num}", callback_data=f"info_{num}")

    builder.adjust(4)
    await message.answer("Статус (✅-своб, ❌-занят). Нажми на ❌ чтобы узнать кто занял:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("info_"), F.from_user.id == ADMIN_ID)
async def link_info(callback: types.CallbackQuery):
    num = callback.data.split("_")[1]
    user_db = load_json(DB_FILE)
    user_info = next((v for v in user_db.values() if v['num'] == num), None)
    
    if user_info:
        await callback.answer(f"Занял: @{user_info['username']}\nID: {user_info['user_id']}", show_alert=True)
    else:
        await callback.answer(f"Номер {num} пока свободен", show_alert=True)

@dp.message(F.text == "📥 Добавить ссылки", F.from_user.id == ADMIN_ID)
async def start_add_links(message: types.Message, state: FSMContext):
    await state.set_state(AdminState.waiting_for_links)
    await message.answer("Пришли список ссылок (каждая с новой строки):")

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def process_adding_links(message: types.Message, state: FSMContext):
    new_links = [l.strip() for l in message.text.split('\n') if l.strip().startswith('http')]
    if not new_links:
        return await message.answer("Ссылок не найдено. Попробуй еще раз.")

    links_db = load_json(LINKS_FILE)
    start_idx = 1
    if links_db:
        nums = [int(n) for n in links_db.keys() if n.isdigit()]
        if nums: start_idx = max(nums) + 1

    for i, link in enumerate(new_links, start=start_idx):
        links_db[str(i)] = link
    
    save_json(LINKS_FILE, links_db)
    await state.clear()
    await message.answer(f"✅ Добавлено {len(new_links)} ссылок. Всего в базе: {len(links_db)}")

@dp.message(F.text == "🧹 Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_links(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {})
    await message.answer("Все данные очищены.")

# --- ЗАПУСК ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
