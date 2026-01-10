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
# Берем ID админа из .env
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0])

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "data_storage.json"
LINKS_FILE = "links.json"
ALLOWED_TRAINERS_FILE = "allowed_trainers.json"
USERS_REGISTRY = "users_registry.json" # Файл для связи кодов и ID

# ================== JSON ХЕЛПЕРЫ ==================

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
        data = [str(ADMIN_ID)]
        save_json(ALLOWED_TRAINERS_FILE, data)
    return data

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

# ================== ЛОГИКА КОДОВ ==================

def get_or_create_user_code(user_id, username):
    registry = load_json(USERS_REGISTRY)
    user_id_str = str(user_id)
    
    # Если юзер уже есть, возвращаем его код
    for code, data in registry.items():
        if data['id'] == user_id:
            return code
    
    # Если нет, создаем новый 6-значный буквенный код
    new_code = ''.join(random.choice(string.ascii_lowercase) for _ in range(6))
    registry[new_code] = {"id": user_id, "username": username}
    save_json(USERS_REGISTRY, registry)
    return new_code

# ================== ОБРАБОТЧИКИ ==================

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    
    user_code = get_or_create_user_code(message.from_user.id, message.from_user.username)
    
    # Уведомление админу
    await bot.send_message(
        ADMIN_ID, 
        f"👤 Новый пользователь!\nID: `{message.from_user.id}`\nUser: @{message.from_user.username}\nКод: `{user_code}`",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await message.answer(
        f"Твой личный код: `{user_code}`\n\n"
        f"**УВАЖНО!!**\nЦе код для смс, обов'язково збережи його.",
        reply_markup=main_menu(),
        parse_mode=ParseMode.MARKDOWN
    )

# Команда для админа: /go [код] [текст]
@dp.message(Command("go"), F.from_user.id == ADMIN_ID)
async def admin_send_message(message: types.Message, command: CommandObject):
    if not command.args:
        return await message.answer("Ошибка! Формат: `/go код текст`", parse_mode=ParseMode.MARKDOWN)
    
    args = command.args.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("Напиши текст после кода!")
    
    target_code = args[0].lower()
    text_to_send = args[1]
    
    registry = load_json(USERS_REGISTRY)
    if target_code not in registry:
        return await message.answer(f"❌ Код `{target_code}` не найден", parse_mode=ParseMode.MARKDOWN)
    
    target_id = registry[target_code]['id']
    
    try:
        await bot.send_message(target_id, text_to_send)
        await message.answer(f"✅ Сообщение отправлено пользователю `{target_code}`")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}")

# ================== ОСТАЛЬНОЙ ФУНКЦИОНАЛ (БЕЗ ИЗМЕНЕНИЙ) ==================

@dp.message(F.text == "🏠 Главное меню")
async def back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Админ-панель:", reply_markup=admin_menu())

# (Тут должны быть остальные ваши функции RegState, ReportState и т.д. из вашего кода)
# Я их опустил для краткости, но они совместимы.

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
