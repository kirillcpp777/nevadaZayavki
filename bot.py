import asyncio
import logging
import os
import random
import string
import json
import re  # Добавили для поиска ссылок и парсинга чисел
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
    await message.answer("Добро пожаловать! Воспользуйся меню:", reply_markup=main_menu())

@dp.message(F.text == "🏠 Главное меню")
async def back_home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())

# --- ЛОГИКА ВЫДАЧИ (ТЕКСТОМ) ---

@dp.message(F.text == "🔗 ПОЛУЧИТЬ ССЫЛКИ")
async def show_free_links_text(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    # Проверка, нет ли уже ссылки
    for data in user_db.values():
        if data.get('user_id') == message.from_user.id:
            return await message.answer(f"У тебя уже есть номер {data['num']}!\n🔗 Ссылка: {data['link']}")

    if not links_db:
        return await message.answer("Свободных ссылок пока нет.")

    taken_nums = [str(item['num']) for item in user_db.values()]
    free_nums = [int(n) for n in links_db.keys() if n not in taken_nums and n.isdigit()]
    
    if not free_nums:
        return await message.answer("Все номера заняты!")

    free_nums.sort()
    
    # Формируем красивый список (например: 1-5, 10, 15-20)
    ranges = []
    if free_nums:
        start = free_nums[0]
        for i in range(1, len(free_nums)):
            if free_nums[i] != free_nums[i-1] + 1:
                ranges.append(f"{start}-{free_nums[i-1]}" if start != free_nums[i-1] else f"{start}")
                start = free_nums[i]
        ranges.append(f"{start}-{free_nums[-1]}" if start != free_nums[-1] else f"{start}")

    text = "✅ <b>Свободные номера:</b>\n" + ", ".join(ranges)
    text += "\n\nПиши номер или диапазон (например: <code>90</code> или <code>90-95</code>):"
    
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(lambda msg: any(char.isdigit() for char in msg.text) and not msg.text.startswith('/'))
async def process_text_selection(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    # Проверка на наличие ссылки
    for data in user_db.values():
        if data.get('user_id') == message.from_user.id:
            return # Игнорируем, если уже есть

    # Парсим ввод (поддерживает "90", "90-95", "90 91")
    requested_nums = []
    # Ищем диапазоны типа 90-95
    ranges = re.findall(r'(\d+)\s*-\s*(\d+)', message.text)
    for r in ranges:
        for n in range(int(r[0]), int(r[1]) + 1):
            requested_nums.append(str(n))
    
    # Ищем одиночные числа, которые не попали в диапазоны
    singles = re.findall(r'\b\d+\b', message.text)
    requested_nums.extend([n for n in singles if n not in requested_nums])

    if not requested_nums:
        return

    taken_nums = [str(item['num']) for item in user_db.values()]
    
    assigned = []
    for num in requested_nums:
        if num in links_db and num not in taken_nums:
            # Выдаем первую попавшуюся свободную из списка
            unique_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
            link = links_db[num]
            
            user_db[unique_code] = {
                "user_id": message.from_user.id,
                "num": num,
                "username": message.from_user.username or "NoName",
                "link": link
            }
            save_json(DB_FILE, user_db)
            
            await message.answer(
                f"✅ <b>Номер {num} закреплен!</b>\n🔗 {link}\n🔑 Код: <code>{unique_code}</code>",
                parse_mode=ParseMode.HTML
            )
            
            await bot.send_message(ADMIN_ID, f"🔔 Новый трафер: @{message.from_user.username}\nНомер: {num}\nКод: {unique_code}")
            return # Выдаем только ОДНУ ссылку за раз

    await message.answer("Выбранные номера заняты или не существуют. Попробуй другие.")

# --- АДМИНКА ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Панель управления:", reply_markup=admin_menu())

@dp.message(F.text == "📥 Добавить ссылки", F.from_user.id == ADMIN_ID)
async def admin_add_start(message: types.Message, state: FSMContext):
    await state.set_state(AdminState.waiting_for_links)
    await message.answer("Просто перешли список с сылками сюда. Бот сам их вытащит.")

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def admin_process_links(message: types.Message, state: FSMContext):
    links_found = re.findall(r'(https?://[^\s]+)', message.text)
    if not links_found:
        return await message.answer("Ссылок не найдено.")

    links_db = load_json(LINKS_FILE)
    curr_max = 0
    if links_db:
        nums = [int(n) for n in links_db.keys() if n.isdigit()]
        if nums: curr_max = max(nums)

    for i, link in enumerate(links_found, start=curr_max + 1):
        links_db[str(i)] = link
    
    save_json(LINKS_FILE, links_db)
    await state.clear()
    await message.answer(f"✅ Добавлено {len(links_found)} ссылок.", reply_markup=admin_menu())

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
    
    if len(report) > 4000: # Защита от слишком длинных сообщений
        await message.answer("База слишком большая, скину файлом позже.")
    else:
        await message.answer(report, parse_mode=ParseMode.HTML)

@dp.message(F.text == "🧹 Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_all(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {})
    await message.answer("Все очищено.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
