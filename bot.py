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

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0])

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "data_storage.json"
LINKS_FILE = "links.json"

# --- Функции работы с JSON ---
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

class RegState(StatesGroup):
    waiting_for_num = State()

class AdminState(StatesGroup):
    waiting_for_links = State()

# --- Клавиатуры ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Создать обращение")],
            [KeyboardButton(text="ПОЛУЧИТЬ ССЫЛКИ")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить ссылки"), KeyboardButton(text="Очистить ссылки")],
            [KeyboardButton(text="Главное меню")]
        ],
        resize_keyboard=True
    )

# --- Основная логика ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Используйте меню для работы с ботом:", reply_markup=main_menu())

@dp.message(F.text == "Главное меню")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вернулись в главное меню:", reply_markup=main_menu())

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def start_reg(message: types.Message, state: FSMContext):
    links_db = load_json(LINKS_FILE)
    if not links_db:
        return await message.answer("База ссылок пуста. Обратитесь к администратору.")

    user_db = load_json(DB_FILE)
    taken_nums = [str(item['num']) for item in user_db.values()]
    free_nums = sorted([n for n in links_db.keys() if n not in taken_nums], key=int)
    
    if not free_nums:
        return await message.answer("Все доступные номера уже заняты.")

    unique_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    available_preview = ", ".join(free_nums[:15])
    
    await message.answer(
        f"Ваш код сессии: `{(unique_code)}` \n\n"
        f"**Доступные номера:** {available_preview}...\n\n"
        f"Введите номер или диапазон (например `96-100`):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    await state.update_data(temp_code=unique_code)
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_num(message: types.Message, state: FSMContext):
    input_text = message.text.strip().replace(" ", "")
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    taken_nums = {str(item['num']): True for item in user_db.values()}
    
    requested_nums = []
    
    if "-" in input_text:
        try:
            parts = input_text.split("-")
            start_n, end_n = int(parts[0]), int(parts[1])
            if start_n > end_n: start_n, end_n = end_n, start_n
            requested_nums = [str(i) for i in range(start_n, end_n + 1)]
        except:
            return await message.answer("Ошибка формата. Введите например 96-100.")
    else:
        requested_nums = [input_text]

    valid_nums = []
    for n in requested_nums:
        if n not in links_db:
            return await message.answer(f"Номер <b>{n}</b> отсутствует в базе.", parse_mode=ParseMode.HTML)
        if n in taken_nums:
            return await message.answer(f"Номер <b>{n}</b> уже занят.", parse_mode=ParseMode.HTML)
        valid_nums.append(n)

    data = await state.get_data()
    session_code = data['temp_code']
    
    # Используем HTML теги <b> и <code>
    response_msg = "<b>Готово! Ваши ссылки:</b>\n\n"
    for idx, num in enumerate(valid_nums):
        link = links_db[num]
        record_id = f"{session_code}_{idx}" if len(valid_nums) > 1 else session_code
        user_db[record_id] = {
            "user_id": message.from_user.id,
            "num": num,
            "username": message.from_user.username or "none",
            "link": link
        }
        response_msg += f"🔢 Номер <b>{num}</b>: {link}\n"

    save_json(DB_FILE, user_db)
    
    # Код сессии в <code> для копирования нажатием
    await message.answer(
        f"{response_msg}\nКод сессии: <code>{session_code}</code>", 
        reply_markup=main_menu(), 
        parse_mode=ParseMode.HTML
    )
    
    await bot.send_message(
        ADMIN_ID, 
        f"✅ Выдача: @{message.from_user.username}\nНомера: {', '.join(valid_nums)}\nКод: <code>{session_code}</code>", 
        parse_mode=ParseMode.HTML
    )
    await state.clear()

# --- Админка ---

@dp.message(F.text == "Добавить ссылки", F.from_user.id == ADMIN_ID)
async def ask_links(message: types.Message, state: FSMContext):
    await message.answer("Пришлите список. Формат:\n`5 поток - №96: https://...`", parse_mode=ParseMode.MARKDOWN)
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def process_bulk_links(message: types.Message, state: FSMContext):
    lines = message.text.split('\n')
    links_db = load_json(LINKS_FILE)
    count = 0
    
    for line in lines:
        if ":" in line:
            parts = line.split(":", 1)
            # Ищем число именно ПОСЛЕ знака №
            num_match = re.search(r'№(\d+)', parts[0])
            if num_match:
                num_key = num_match.group(1)
                url = parts[1].strip()
                if url.startswith("http"):
                    links_db[num_key] = url
                    count += 1
    
    save_json(LINKS_FILE, links_db)
    await message.answer(f"Успешно добавлено номеров: **{count}**", reply_markup=admin_menu(), parse_mode=ParseMode.MARKDOWN)
    await state.clear()

# Остальные функции (Очистить, Обращение) остаются без изменений
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Панель управления:", reply_markup=admin_menu())

@dp.message(F.text == "Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_all_links(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {})
    await message.answer("Базы данных полностью очищены.")

@dp.message(F.text == "Создать обращение")
async def support_start(message: types.Message):
    await message.answer("Напишите ваш вопрос:")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, ~F.text.in_(["ПОЛУЧИТЬ ССЫЛКИ", "Создать обращение", "Главное меню"]))
async def to_admin(message: types.Message):
    info = f"❓ **ВОПРОС**\nID: `{(message.from_user.id)}` \nЮзер: @{message.from_user.username}\n\n"
    await bot.send_message(ADMIN_ID, info + message.text, parse_mode=ParseMode.MARKDOWN)

@dp.message(F.from_user.id == ADMIN_ID, F.reply_to_message)
async def from_admin(message: types.Message):
    try:
        raw_text = message.reply_to_message.text
        user_id = int(re.search(r'ID:\s*(\d+)', raw_text).group(1))
        await bot.send_message(user_id, f"**ОТВЕТ:**\n\n{message.text}", parse_mode=ParseMode.MARKDOWN)
    except: pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
