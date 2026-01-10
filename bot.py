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

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_IDS").split(",")[0])

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Файлы базы данных
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

# Состояния FSM
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
            [KeyboardButton(text="Рассылка по ID (инфо)")], # Новая кнопка
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )

# --- Обработчики пользователя ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Используйте кнопки меню для работы с ботом:", reply_markup=main_menu())

@dp.message(F.text == "🏠 Главное меню")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вернулись в меню:", reply_markup=main_menu())

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def start_reg(message: types.Message, state: FSMContext):
    links_db = load_json(LINKS_FILE)
    if not links_db:
        return await message.answer("База ссылок пуста. Обратитесь к администратору.")

    user_db = load_json(DB_FILE)
    taken_nums = [str(item['num']) for item in user_db.values()]
    free_nums = sorted([n for n in links_db.keys() if n not in taken_nums], key=lambda x: int(x) if x.isdigit() else 0)
    
    if not free_nums:
        return await message.answer("Все доступные номера уже заняты.")

    unique_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    available_preview = ", ".join(free_nums[:15])
    
    await message.answer(
        f"<b>Доступные номера:</b> {available_preview}...\n\n"
        f"Введите номер (напр. <code>96</code>) или диапазон (напр. <code>96-100</code>):",
        parse_mode=ParseMode.HTML,
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
    
    # Парсинг диапазона или одного номера
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
    
    response_msg = "<b>Ваши ссылки:</b>\n\n"
    for idx, num in enumerate(valid_nums):
        link = links_db[num]
        # Каждая ссылка сохраняется под уникальным ключом для статы
        record_id = f"{session_code}_{idx}" if len(valid_nums) > 1 else session_code
        user_db[record_id] = {
            "user_id": message.from_user.id,
            "num": num,
            "username": message.from_user.username or "none",
            "link": link
        }
        response_msg += f" Номер <b>{num}</b>: {link}\n"

    save_json(DB_FILE, user_db)
    
    await message.answer(response_msg, reply_markup=main_menu(), parse_mode=ParseMode.HTML)
    
    # Уведомление админу (с кодом для статы)
    await bot.send_message(
        ADMIN_ID, 
        f"✅ <b>Выдача:</b> @{message.from_user.username}\n"
        f"🔢 Номера: {', '.join(valid_nums)}\n"
        f"🔑 Код для статы: <code>{session_code}</code>", 
        parse_mode=ParseMode.HTML
    )
    await state.clear()

# --- Админ-панель ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Управление ботом:", reply_markup=admin_menu())

# Подсказка по команде при нажатии на кнопку
@dp.message(F.text == "Рассылка по ID (инфо)", F.from_user.id == ADMIN_ID)
async def go_info(message: types.Message):
    await message.answer(
        "Чтобы отправить сообщение пользователю, используйте команду:\n"
        "<code>/go 12345678 Привет, это сообщение для тебя!</code>",
        parse_mode=ParseMode.HTML
    )

# Сама команда рассылки
@dp.message(Command("go"), F.from_user.id == ADMIN_ID)
async def cmd_go(message: types.Message):
    # Разбиваем текст сообщения: /go (0), id (1), сообщение (2+)
    parts = message.text.split(maxsplit=2)
    
    if len(parts) < 3:
        return await message.answer("❌ Ошибка! Формат: <code>/go {ID} {сообщение}</code>", parse_mode=ParseMode.HTML)
    
    target_id = parts[1]
    text_to_send = parts[2]
    
    if not target_id.isdigit():
        return await message.answer("❌ Ошибка! ID должен состоять только из цифр.")

    try:
        await bot.send_message(
            chat_id=int(target_id),
            text=f"<b>📩 Сообщение от администратора:</b>\n\n{text_to_send}",
            parse_mode=ParseMode.HTML
        )
        await message.answer(f"✅ Сообщение успешно отправлено пользователю <code>{target_id}</code>")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение.\nОшибка: {e}")

@dp.message(F.text == "Добавить ссылки", F.from_user.id == ADMIN_ID)
async def ask_links(message: types.Message, state: FSMContext):
    await message.answer("Пришлите список. Формат:\n<code>5 поток - №96: https://...</code>", parse_mode=ParseMode.HTML)
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links, F.from_user.id == ADMIN_ID)
async def process_bulk_links(message: types.Message, state: FSMContext):
    lines = message.text.split('\n')
    links_db = load_json(LINKS_FILE)
    count = 0
    
    for line in lines:
        if ":" in line:
            parts = line.split(":", 1)
            # Извлекаем только число после знака №
            num_match = re.search(r'№(\d+)', parts[0])
            if num_match:
                num_key = num_match.group(1)
                url = parts[1].strip()
                if url.startswith("http"):
                    links_db[num_key] = url
                    count += 1
    
    save_json(LINKS_FILE, links_db)
    await message.answer(f"Успешно добавлено номеров: <b>{count}</b>", reply_markup=admin_menu(), parse_mode=ParseMode.HTML)
    await state.clear()

@dp.message(F.text == "Очистить ссылки", F.from_user.id == ADMIN_ID)
async def clear_all_links(message: types.Message):
    save_json(LINKS_FILE, {})
    save_json(DB_FILE, {})
    await message.answer("Все базы данных очищены.")

# --- Рассылка статистики и поддержка ---

@dp.message(F.from_user.id == ADMIN_ID, F.photo)
async def admin_send_stats(message: types.Message):
    """Отправка статистики: фото + код сессии в описании"""
    if not message.caption:
        return await message.answer("❌ Напишите код сессии в подписи к фото.")

    user_db = load_json(DB_FILE)
    code = message.caption.strip().lower()
    target_user_id = None

    for key, data in user_db.items():
        if key == code or key.startswith(f"{code}_"):
            target_user_id = data['user_id']
            break

    if target_user_id:
        try:
            await bot.send_photo(
                target_user_id,
                message.photo[-1].file_id,
                caption="<b>📊 Вам пришла статистика!</b>",
                parse_mode=ParseMode.HTML
            )
            await message.answer(f"✅ Статистика по коду <code>{code}</code> отправлена.")
        except Exception as e:
            await message.answer(f"❌ Ошибка отправки: {e}")
    else:
        await message.answer(f"❌ Код <code>{code}</code> не найден в базе.")

@dp.message(F.text == "Создать обращение")
async def support_start(message: types.Message):
    await message.answer("Напишите ваш вопрос ниже 👇")

@dp.message(F.chat.type == "private", F.from_user.id != ADMIN_ID, ~F.text.in_(["ПОЛУЧИТЬ ССЫЛКИ", "Создать обращение", "🏠 Главное меню"]))
async def to_admin(message: types.Message):
    info = f"<b>💬 ВОПРОС</b>\nID: <code>{message.from_user.id}</code>\n👤 @{message.from_user.username}\n\n"
    await bot.send_message(ADMIN_ID, info + message.text, parse_mode=ParseMode.HTML)

@dp.message(F.from_user.id == ADMIN_ID, F.reply_to_message)
async def from_admin(message: types.Message):
    try:
        user_id = int(re.search(r'ID:\s*(\d+)', message.reply_to_message.text).group(1))
        await bot.send_message(user_id, f"<b>👨‍💻 ОТВЕТ:</b>\n\n{message.text}", parse_mode=ParseMode.HTML)
    except: pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
