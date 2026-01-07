import asyncio
import logging
import os
import random
import string
import json
import re  # ОБЯЗАТЕЛЬНО: добавили для поиска ссылок в тексте
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
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
            try: return json.load(f)
            except: return {}
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

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
    await message.answer("Добро пожаловать!", reply_markup=main_menu())

@dp.message(F.text == "🏠 Главное меню")
async def back_home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())

# --- ЛОГИКА ДЛЯ ЮЗЕРА ---

@dp.message(F.text == "🔗 ПОЛУЧИТЬ ССЫЛКИ")
async def show_free_links_text(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    # Проверка, нет ли уже ссылки
    for data in user_db.values():
        if data.get('user_id') == message.from_user.id:
            return await message.answer(f"Твой номер {data['num']}!\n🔗 Ссылка: {data['link']}")

    if not links_db:
        return await message.answer("Свободных ссылок пока нет.")

    taken_nums = [str(item['num']) for item in user_db.values()]
    free_nums = [int(n) for n in links_db.keys() if n not in taken_nums and n.isdigit()]
    
    if not free_nums:
        return await message.answer("Все номера заняты!")

    free_nums.sort()
    
    # Группировка в диапазоны (1-10, 15, 20-30)
    ranges = []
    if free_nums:
        start = free_nums[0]
        for i in range(1, len(free_nums)):
            if free_nums[i] != free_nums[i-1] + 1:
                ranges.append(f"{start}-{free_nums[i-1]}" if start != free_nums[i-1] else f"{start}")
                start = free_nums[i]
        ranges.append(f"{start}-{free_nums[-1]}" if start != free_nums[-1] else f"{start}")

    text = "✅ <b>Свободно:</b>\n" + ", ".join(ranges)
    text += "\n\nПиши номер (напр. <code>95</code>) или диапазон (<code>90-100</code>):"
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(lambda msg: any(char.isdigit() for char in msg.text) and not msg.text.startswith('/'))
async def process_text_selection(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    # Если у юзера уже есть ссылка - игнорим
    if any(d.get('user_id') == message.from_user.id for d in user_db.values()):
        return

    # Парсим ввод: ищем диапазоны и одиночные числа
    requested = []
    found_ranges = re.findall(r'(\d+)\s*-\s*(\d+)', message.text)
    for r in found_ranges:
        for n in range(int(r[0]), int(r[1]) + 1):
            requested.append(str(n))
    
    singles = re.findall(r'\b\d+\b', message.text)
    for s in singles:
        if s not in requested: requested.append(s)

    if not requested: return

    taken_nums = [str(item['num']) for item in user_db.values()]
    
    # Выдаем ОДНУ первую свободную ссылку из запрошенных
    for num in requested:
        if num in links_db and num not in taken_nums:
            unique_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
            link = links_db[num]
            
            user_db[unique_code] = {
                "user_id": message.from_user.id,
                "num": num,
                "username": message.from_user.username or "User",
                "link": link
            }
            save_json(DB_FILE, user_db)
            
            await message.answer(f"✅ <b>Номер {num} выдан!</b>\n🔗 {link}\n🔑 Твой код: <code>{unique_code}</code>", parse_mode=ParseMode.HTML)
            await bot.send_message(ADMIN_ID, f"🔔 Выдан номер {num} юзеру @{message.from_user.username}")
            return

    await message.answer("Эти номера заняты или их нет в базе.")

# --- АДМИНКА ---

# Вход в админку
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("🤖 Вы вошли в режим администратора", reply_markup=admin_menu())

@dp.message(F.text == "📥 Добавить ссылки", F.from_user.id == ADMIN_ID)
async def admin_add_start(message: types.Message, state: FSMContext):
    await state.set_state(AdminState.waiting_for_links)
    await message.answer("Пришли сообщение с ссылками. Я вытащу их автоматически.")

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def admin_process_links(message: types.Message, state: FSMContext):
    # Улучшенный поиск: №(число) любой_текст (ссылка)
    items_found = re.findall(r'№(\d+).*?(https?://\S+)', message.text, re.DOTALL)
    
    links_db = load_json(LINKS_FILE)
    
    if not items_found:
        links_only = re.findall(r'(https?://\S+)', message.text)
        if not links_only:
            return await message.answer("❌ Ссылок не найдено. Проверь формат.")
        
        curr_max = max([int(n) for n in links_db.keys() if n.isdigit()] or [0])
        for i, link in enumerate(links_only, start=curr_max + 1):
            links_db[str(i)] = link
        msg_text = f"✅ Добавлено {len(links_only)} ссылок по порядку."
    else:
        for num, link in items_found:
            links_db[str(num)] = link
        msg_text = f"✅ Добавлено {len(items_found)} ссылок с вашими номерами."

    save_json(LINKS_FILE, links_db)
    await state.clear()
    await message.answer(f"{msg_text}\nВсего в базе: {len(links_db)}", reply_markup=admin_menu())
    
@dp.message(F.text == "📊 Статус ссылок", F.from_user.id == ADMIN_ID)
async def admin_status(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    if not links_db: return await message.answer("База пуста.")
    
    taken = {item['num']: item['username'] for item in user_db.values()}
    report = "<b>Статус:</b>\n"
    for n in sorted(links_db.keys(), key=int):
        status = f"❌ (@{taken[n]})" if n in taken else "✅"
        report += f"{n}: {status}\n"
    
    await message.answer(report[:4000], parse_mode=ParseMode.HTML)

@dp.message(F.text == "🧹 Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_all(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {})
    await message.answer("База очищена.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
