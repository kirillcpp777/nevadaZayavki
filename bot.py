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
# Берем ID админа из .env
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0]) 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Файлы БД
DB_FILE = "data_storage.json"
LINKS_FILE = "links.json"

# --- Функции работы с БД ---
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Состояния
class RegState(StatesGroup):
    waiting_for_num = State()

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
            [KeyboardButton(text="📥 Добавить ссылки"), KeyboardButton(text="🧹 Очистить ссылки")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )

# --- Обработчики Общие ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Воспользуйся меню ниже:", reply_markup=main_menu())

@dp.message(F.text == "🏠 Главное меню")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вернулись в меню:", reply_markup=main_menu())

# --- Логика регистрации и выдачи ---

@dp.message(F.text == "🔗 ПОЛУЧИТЬ ССЫЛКИ")
async def start_reg(message: types.Message, state: FSMContext):
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    if not links_db:
        return await message.answer("Админ еще не загрузил ссылки. Обратитесь в поддержку.")

    # Проверка: не занимал ли юзер уже номер
    for code, data in user_db.items():
        if data.get('user_id') == message.from_user.id:
            return await message.answer(f"Ты уже занял номер {data['num']}!\nСсылка: {data['link']}")

    taken_nums = [str(item['num']) for item in user_db.values()]
    free_nums = [n for n in links_db.keys() if n not in taken_nums]
    
    if not free_nums:
        return await message.answer("К сожалению, все свободные номера разобрали.")

    unique_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    available_str = ", ".join(free_nums[:15])
    
    await message.answer(
        f"Твой уникальный код: <code>{unique_code}</code>\n\n"
        f"<b>Свободные номера:</b> {available_str}...\n"
        f"Введи номер, который хочешь занять:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    await state.update_data(temp_code=unique_code)
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_num(message: types.Message, state: FSMContext):
    num = message.text.strip()
    links_db = load_json(LINKS_FILE)
    user_db = load_json(DB_FILE)
    
    if num not in links_db:
        return await message.answer("Такого номера нет в списке доступных. Введи правильный номер:")

    taken_nums = [str(item['num']) for item in user_db.values()]
    if num in taken_nums:
        return await message.answer(f"Номер {num} уже занят. Выбери другой:")

    data = await state.get_data()
    code = data['temp_code']
    link = links_db[num]

    user_db[code] = {
        "user_id": message.from_user.id,
        "num": num,
        "username": message.from_user.username,
        "link": link
    }
    save_json(DB_FILE, user_db)

    await message.answer(
        f"✅ Ты успешно пронумеровался!\n"
        f"🔢 Твой номер: <b>{num}</b>\n"
        f"🔗 Ссылка: {link}\n\n"
        f"Жди статистику!",
        reply_markup=main_menu(),
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Новая регистрация!</b>\n👤 @{message.from_user.username}\n🔢 Номер: {num}\n🔑 Код: {code}",
        parse_mode=ParseMode.HTML
    )

# --- Админ-панель ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Управление ссылками включено:", reply_markup=admin_menu())

@dp.message(F.text == "📥 Добавить ссылки", F.from_user.id == ADMIN_ID)
async def ask_links(message: types.Message, state: FSMContext):
    await message.answer("Отправь список ссылок. Формат:\n<code>5 поток - №70: https://t.me/...</code>", parse_mode=ParseMode.HTML)
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def process_bulk_links(message: types.Message, state: FSMContext):
    lines = message.text.split('\n')
    links_db = load_json(LINKS_FILE)
    count = 0
    
    for line in lines:
        if ":" in line:
            # Парсим номер: убираем лишний текст до двоеточия
            parts = line.split(":", 1)
            num_part = parts[0].replace("5 поток - №", "").replace("№", "").strip()
            url_part = parts[1].strip()
            if num_part and url_part.startswith("http"):
                links_db[num_part] = url_part
                count += 1
    
    save_json(LINKS_FILE, links_db)
    await message.answer(f"✅ Успешно загружено ссылок: {count}", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "🧹 Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_all_links(message: types.Message):
    save_json(LINKS_FILE, {})
    await message.answer("🗑 Все ссылки удалены из базы данных.")

# --- Рассылка статы и поддержка (твой старый код) ---

@dp.message(F.from_user.id == ADMIN_ID, F.photo)
async def admin_send_photo(message: types.Message):
    if not message.caption: return
    target_code = message.caption.strip().lower()
    user_db = load_json(DB_FILE)
    if target_code in user_db:
        try:
            await bot.send_photo(user_db[target_code]['user_id'], message.photo[-1].file_id, 
                               caption=f"📊 Статистика: <code>{target_code}</code>", parse_mode=ParseMode.HTML)
            await message.answer("Отправлено.")
        except: await message.answer("Ошибка при отправке.")

@dp.message(F.text == "🆘 Создать обращение")
async def support_start(message: types.Message):
    await message.answer("Напиши свой вопрос ниже 👇")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, ~F.text.in_(["🔗 ПОЛУЧИТЬ ССЫЛКИ", "🆘 Создать обращение", "🏠 Главное меню"]))
async def to_admin(message: types.Message):
    info = f"<b>💬 ВОПРОС</b>\nID: <code>{message.from_user.id}</code>\n👤 @{message.from_user.username}\n\n"
    await bot.send_message(ADMIN_ID, info + message.text, parse_mode=ParseMode.HTML)

@dp.message(F.from_user.id == ADMIN_ID, F.reply_to_message)
async def from_admin(message: types.Message):
    try:
        user_id = int(message.reply_to_message.text.split("ID:")[1].split("\n")[0].strip())
        await bot.send_message(user_id, f"<b>👨‍💻 ОТВЕТ:</b>\n\n{message.text}", parse_mode=ParseMode.HTML)
    except: pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
