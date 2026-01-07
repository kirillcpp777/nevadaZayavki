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
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0])

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "data_storage.json"
LINKS_FILE = "links.json"

# --- Работа с БД ---
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
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

# --- Обработчики ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Добро пожаловать. Используйте меню для навигации:", reply_markup=main_menu())

@dp.message(F.text == "Главное меню")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы перешли в главное меню:", reply_markup=main_menu())

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def start_reg(message: types.Message, state: FSMContext):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    if not links_db:
        return await message.answer("База ссылок пуста. Обратитесь к администратору.")

    taken_nums = [str(item['num']) for item in user_db.values()]
    free_nums = [n for n in links_db.keys() if n not in taken_nums]
    
    if not free_nums:
        return await message.answer("Свободные номера отсутствуют.")

    unique_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    available_str = ", ".join(free_nums[:15])
    
    await message.answer(
        f"Ваш код для этой сессии: `{(unique_code)}` \n\n"
        f"*Доступные номера:* {available_str}...\n"
        f"Введите номер или диапазон (например, 97-100):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    await state.update_data(temp_code=unique_code)
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_num(message: types.Message, state: FSMContext):
    input_text = message.text.strip()
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    taken_nums = [str(item['num']) for item in user_db.values()]
    
    requested_nums = []
    
    # Обработка диапазона
    if "-" in input_text:
        try:
            start_n, end_n = map(int, input_text.split("-"))
            requested_nums = [str(i) for i in range(start_n, end_n + 1)]
        except ValueError:
            return await message.answer("Неверный формат диапазона. Введите число или 'начало-конец'.")
    else:
        requested_nums = [input_text]

    # Проверка наличия и доступности
    results = []
    for n in requested_nums:
        if n not in links_db:
            return await message.answer(f"Номер *{n}* отсутствует в базе.")
        if n in taken_nums:
            return await message.answer(f"Номер *{n}* уже занят.")
        results.append(n)

    data = await state.get_data()
    base_code = data['temp_code']
    
    # Сохраняем каждый номер отдельно
    response_links = []
    for idx, n in enumerate(results):
        # Если номеров много, создаем под-коды или привязываем к основному
        current_code = f"{base_code}_{idx}" if len(results) > 1 else base_code
        link = links_db[n]
        
        user_db[current_code] = {
            "user_id": message.from_user.id,
            "num": n,
            "username": message.from_user.username,
            "link": link
        }
        response_links.append(f"Номер *{n}*: {link}")

    save_json(DB_FILE, user_db)

    links_text = "\n".join(response_links)
    await message.answer(
        f"*Регистрация завершена*\n\n{links_text}\n\n"
        f"Код для статистики: `{(base_code)}`",
        reply_markup=main_menu(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    await bot.send_message(
        ADMIN_ID,
        f"Новая выдача: @{message.from_user.username}\nНомера: *{', '.join(results)}*\nКод: `{(base_code)}`"
    )
    await state.clear()

# --- Админ-панель ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Панель администратора:", reply_markup=admin_menu())

@dp.message(F.text == "Добавить ссылки", F.from_user.id == ADMIN_ID)
async def ask_links(message: types.Message, state: FSMContext):
    await message.answer("Введите список ссылок в формате:\n`№70: https://t.me/...`", parse_mode=ParseMode.MARKDOWN)
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def process_bulk_links(message: types.Message, state: FSMContext):
    lines = message.text.split('\n')
    links_db = load_json(LINKS_FILE)
    count = 0
    
    for line in lines:
        if ":" in line:
            parts = line.split(":", 1)
            num_part = parts[0].replace("5 поток - №", "").replace("№", "").strip()
            url_part = parts[1].strip()
            if num_part and url_part.startswith("http"):
                links_db[num_part] = url_part
                count += 1
    
    save_json(LINKS_FILE, links_db)
    await message.answer(f"База обновлена. Добавлено: *{count}*", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_all_links(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {}) # Очищаем и базу занятых номеров
    await message.answer("Все базы данных очищены.")

# --- Поддержка ---

@dp.message(F.text == "Создать обращение")
async def support_start(message: types.Message):
    await message.answer("Отправьте ваш вопрос одним сообщением:")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, ~F.text.in_(["ПОЛУЧИТЬ ССЫЛКИ", "Создать обращение", "Главное меню"]))
async def to_admin(message: types.Message):
    info = f"*ОБРАЩЕНИЕ*\nID: `{(message.from_user.id)}` \nЮзер: @{message.from_user.username}\n\n"
    await bot.send_message(ADMIN_ID, info + message.text, parse_mode=ParseMode.MARKDOWN)

@dp.message(F.from_user.id == ADMIN_ID, F.reply_to_message)
async def from_admin(message: types.Message):
    try:
        # Извлекаем ID из текста сообщения, на которое отвечаем
        raw_id = message.reply_to_message.text.split("ID:")[1].split("\n")[0].strip()
        user_id = int(''.join(filter(str.isdigit, raw_id)))
        await bot.send_message(user_id, f"*ОТВЕТ АДМИНИСТРАТОРА:*\n\n{message.text}", parse_mode=ParseMode.MARKDOWN)
    except:
        pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
