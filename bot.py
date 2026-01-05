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
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Ваш цифровой ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Состояния ---
class SupportState(StatesGroup):
    waiting_for_data = State()

# --- Клавиатуры ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🆘 Создать обращение")]],
        resize_keyboard=True
    )

# --- Обработчики ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        f"Приветствуем, {message.from_user.first_name}.\n\n"
        "Данный бот предназначен для прямой связи с администрацией.\n"
        "Нажмите кнопку ниже, чтобы изложить суть вашего вопроса.",
        reply_markup=main_menu()
    )

@dp.message(F.text == "🆘 Создать обращение")
async def start_support(message: types.Message, state: FSMContext):
    await state.set_state(SupportState.waiting_for_data)
    await message.answer(
        "Пожалуйста, прикрепите фото (если есть) и введите описание проблемы в одном сообщении.",
        reply_markup=types.ReplyKeyboardRemove()
    )

# Получение данных от пользователя и пересылка вам
@dp.message(SupportState.waiting_for_data)
async def process_report(message: types.Message, state: FSMContext):
    try:
        # Формируем заголовок для админа
        info = (
            f"<b>НОВОЕ ОБРАЩЕНИЕ</b>\n"
            f"──────────────────\n"
            f"👤 От: {message.from_user.full_name}\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"──────────────────\n"
        )

        if message.photo:
            # Отправка фото с описанием
            caption = info + (message.caption if message.caption else "<i>Описание отсутствует</i>")
            await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=caption, parse_mode=ParseMode.HTML)
        else:
            # Отправка только текста
            await bot.send_message(chat_id=ADMIN_ID, text=info + message.text, parse_mode=ParseMode.HTML)

        await message.answer("Ваше обращение принято. Ожидайте ответа специалиста.", reply_markup=main_menu())
        await state.clear()
        
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("Произошла техническая ошибка. Попробуйте позже.")

# Ответ администратора пользователю (через Reply)
@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        # Извлекаем ID из текста сообщения, на которое отвечаем
        reply_text = message.reply_to_message.text or message.reply_to_message.caption
        if "ID:" in reply_text:
            user_id = int(reply_text.split("ID:")[1].split("\n")[0].strip())
            
            prefix = "<b>ОТВЕТ АДМИНИСТРАЦИИ:</b>\n\n"
            
            if message.photo:
                await bot.send_photo(
                    chat_id=user_id, 
                    photo=message.photo[-1].file_id, 
                    caption=prefix + (message.caption if message.caption else ""),
                    parse_mode=ParseMode.HTML
                )
            else:
                await bot.send_message(chat_id=user_id, text=prefix + message.text, parse_mode=ParseMode.HTML)
            
            await message.answer("✅ Ответ успешно доставлен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
