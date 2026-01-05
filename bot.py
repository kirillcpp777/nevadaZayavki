import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

# --- Конфигурация ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPER_ADMIN_ID = 5553120504
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS").split(",")]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Состояния ---
class SupportState(StatesGroup):
    is_chatting = State() # Состояние активного диалога

# --- Клавиатуры ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🆘 Создать обращение")]],
        resize_keyboard=True
    )

def close_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Завершить вопрос")]],
        resize_keyboard=True
    )

# --- Обработчики ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Приветствуем, {message.from_user.first_name}.\n\n"
        "Нажмите на кнопку ниже, чтобы начать общение с поддержкой.",
        reply_markup=main_menu()
    )

@dp.message(F.text == "🆘 Создать обращение")
async def start_support(message: types.Message, state: FSMContext):
    await state.set_state(SupportState.is_chatting)
    await message.answer(
        "Диалог открыт. Теперь всё, что вы напишете или пришлете (фото), "
        "будет передано администрации.\n\n"
        "Когда ваш вопрос будет решен, нажмите кнопку ниже 👇",
        reply_markup=close_kb()
    )

@dp.message(F.text == "✅ Завершить вопрос", SupportState.is_chatting)
async def close_support(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Диалог завершен. Спасибо за обращение!", reply_markup=main_menu())
    
    # Уведомляем админов, что юзер закрыл тикет
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"🔘 Пользователь {message.from_user.full_name} (ID: {message.from_user.id}) завершил диалог.")

# --- Пересылка сообщений от клиента админам ---
@dp.message(SupportState.is_chatting)
async def process_chat(message: types.Message):
    # Игнорируем кнопку закрытия, она обработана выше
    if message.text == "✅ Завершить вопрос":
        return

    info = (
        f"<b>💬 СООБЩЕНИЕ ОТ КЛИЕНТА</b>\n"
        f"👤 От: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"──────────────────\n"
    )

    for admin_id in ADMIN_IDS:
        try:
            if message.photo:
                await bot.send_photo(admin_id, message.photo[-1].file_id, 
                                     caption=info + (message.caption or ""), parse_mode=ParseMode.HTML)
            else:
                await bot.send_message(admin_id, info + message.text, parse_mode=ParseMode.HTML)
        except:
            pass

# --- Ответ админа (через Reply) ---
@dp.message(F.chat.id.in_(ADMIN_IDS), F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption
        if reply_text and "ID:" in reply_text:
            # Парсим ID юзера из сообщения, на которое отвечаем
            user_id = int(reply_text.split("ID:")[1].split("\n")[0].strip())
            
            user_msg_header = "<b>👨‍💻 ОТВЕТ АДМИНИСТРАЦИИ:</b>\n\n"
            
            # Отправляем юзеру
            if message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, 
                                     caption=user_msg_header + (message.caption or ""), parse_mode=ParseMode.HTML)
            else:
                await bot.send_message(user_id, user_msg_header + message.text, parse_mode=ParseMode.HTML)
            
            await message.answer(f"✅ Отправлено пользователю {user_id}.")

            # Дубликат вам в личку, если ответил помощник
            if message.from_user.id != SUPER_ADMIN_ID:
                log_msg = (
                    f"<b>🔔 КОПИЯ ОТВЕТА ПОМОЩНИКА</b>\n"
                    f"👤 Помощник: {message.from_user.full_name}\n"
                    f"👤 Кому (ID): {user_id}\n"
                    f"──────────────────\n"
                    f"📝 Текст: {message.text or message.caption or '[Медиа]'}"
                )
                await bot.send_message(SUPER_ADMIN_ID, log_msg, parse_mode=ParseMode.HTML)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

async def main():
    print("Бот в режиме чата запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
