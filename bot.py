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

# --- Налаштування ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Ваш ID в Телеграм

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Стан (FSM) ---
class SupportState(StatesGroup):
    waiting_for_issue = State()

# --- Клавіатури ---
def main_menu():
    kb = [
        [KeyboardButton(text="🆘 Написати проблему")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Обробники ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        f"Вітаю, {message.from_user.full_name}! 👋\n\n"
        "Якщо у вас виникла проблема, натисніть кнопку нижче і опишіть її.",
        reply_markup=main_menu()
    )

@dp.message(F.text == "🆘 Написати проблему")
async def start_support(message: types.Message, state: FSMContext):
    await state.set_state(SupportState.waiting_for_issue)
    await message.answer(
        "📝 **Опишіть вашу проблему.**\n"
        "Ви можете надіслати текст разом з фото одним повідомленням.",
        reply_markup=types.ReplyKeyboardRemove() # Прибираємо кнопку на час запису
    )

# Обробка повідомлення від користувача (текст або фото)
@dp.message(SupportState.waiting_for_issue)
async def process_issue(message: types.Message, state: FSMContext):
    # Відправляємо адміну (вам)
    try:
        # Інформація про відправника
        header = (
            f"📩 <b>НОВА ЗАЯВКА</b>\n"
            f"👤 Від: {message.from_user.mention_html()}\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"──────────────────\n"
        )

        if message.photo:
            # Якщо є фото, копіюємо його адміну з підписом
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=message.photo[-1].file_id,
                caption=header + (message.caption if message.caption else "Без опису (тільки фото)"),
                parse_mode=ParseMode.HTML
            )
        else:
            # Якщо тільки текст
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=header + message.text,
                parse_mode=ParseMode.HTML
            )

        await message.answer("✅ Ваше повідомлення надіслано адміністратору. Очікуйте на відповідь!", reply_markup=main_menu())
        await state.clear()
        
    except Exception as e:
        logging.error(f"Error sending to admin: {e}")
        await message.answer("❌ Сталася помилка при відправці. Спробуйте пізніше.")

# Функція відповіді (тільки для адміна)
# Щоб відповісти користувачу, адмін має зробити REPlY (відповісти) на повідомлення бота
@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def admin_reply(message: types.Message):
    try:
        # Дістаємо ID користувача з тексту (ми його туди спеціально вписали)
        # Або простіший варіант - парсимо переслане повідомлення
        text = message.reply_to_message.text or message.reply_to_message.caption
        if "ID:" in text:
            user_id = int(text.split("ID:")[1].split("\n")[0].strip())
            
            if message.photo:
                await bot.send_photo(chat_id=user_id, photo=message.photo[-1].file_id, caption=f"<b>Відповідь від адміністратора:</b>\n\n{message.caption if message.caption else ''}", parse_mode=ParseMode.HTML)
            else:
                await bot.send_message(chat_id=user_id, text=f"<b>Відповідь від адміністратора:</b>\n\n{message.text}", parse_mode=ParseMode.HTML)
            
            await message.answer("✅ Відповідь надіслана!")
    except Exception as e:
        await message.answer(f"❌ Помилка при відповіді: {e}")

async def main():
    logging.info("Бот підтримки запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
