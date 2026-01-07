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
    await message.answer("Пришли сообщение с ссылками.\n\n📝 Примеры форматов:\n• 5 поток - №90: https://...\n• №91: https://...\n• Просто ссылки (автонумерация)")

# --- ВСЕЯДНЫЙ ОБРАБОТЧИК (ФАЙЛЫ + ТЕКСТ) ---

async def parse_and_save_links(content: str, links_db: dict):
    lines = content.split('\n')
    added_count = 0
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Ищем ссылку
        link_match = re.search(r'https?://\S+', line)
        if link_match:
            link = link_match.group(0)
            # Ищем число для номера
            num_match = re.search(r'(\d+)', line)
            
            if num_match:
                num = num_match.group(1)
                links_db[str(num)] = link
            else:
                curr_max = max([int(n) for n in links_db.keys() if n.isdigit()] or [0])
                links_db[str(curr_max + 1)] = link
            added_count += 1
    return added_count

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def admin_process_links_combined(message: types.Message, state: FSMContext):
    links_db = load_json(LINKS_FILE)
    content = ""

    # Если прислали файл
    if message.document:
        if not message.document.file_name.endswith('.txt'):
            return await message.answer("❌ Брат, принимаю только .txt файлы!")
        
        file = await bot.get_file(message.document.file_id)
        file_buffer = await bot.download_file(file.file_path)
        content = file_buffer.read().decode('utf-8')
    
    # Если прислали просто текст
    elif message.text:
        content = message.text

    if not content:
        return await message.answer("❌ Пусто. Скинь текст или .txt файл.")

    added = await parse_and_save_links(content, links_db)

    if added > 0:
        save_json(LINKS_FILE, links_db)
        await state.clear()
        await message.answer(f"✅ Красава! Добавлено ссылок: {added}\n📊 Всего в базе: {len(links_db)}", reply_markup=admin_menu())
    else:
        await message.answer("❌ Не нашел ссылок в файле/сообщении. Проверь содержимое.")
@dp.message(F.text == "📊 Статус ссылок", F.from_user.id == ADMIN_ID)
async def admin_status(message: types.Message):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    if not links_db: return await message.answer("База пуста.")
    
    taken = {item['num']: item['username'] for item in user_db.values()}
    report = "<b>📊 Статус базы ссылок:</b>\n\n"
    
    # Правильная сортировка по числовому значению
    sorted_nums = sorted(links_db.keys(), key=lambda x: int(x) if x.isdigit() else 999999)
    
    for n in sorted_nums:
        status = f"❌ @{taken[n]}" if n in taken else "✅ свободен"
        link = links_db[n]
        report += f"<b>№{n}:</b> {status}\n<code>{link}</code>\n\n"
    
    # Отправляем по частям если слишком длинно
    if len(report) > 4000:
        parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
        for part in parts:
            await message.answer(part, parse_mode=ParseMode.HTML)
    else:
        await message.answer(report, parse_mode=ParseMode.HTML)

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
