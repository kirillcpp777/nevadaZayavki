import asyncio
import logging
import os
import json
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
import gspread_asyncio
from google.oauth2.service_account import Credentials

load_dotenv()

# Налаштування
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
# Тепер беремо вміст JSON прямо з тексту змінної
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def get_scoped_credentials():
    if not GOOGLE_CREDS_JSON:
        logging.error("Змінна GOOGLE_CREDS_JSON порожня!")
        return None
    
    try:
        # 1. Прибираємо зайві лапки, які Railway іноді додає навколо всього тексту
        raw_json = GOOGLE_CREDS_JSON.strip()
        if raw_json.startswith('"') and raw_json.endswith('"'):
            raw_json = raw_json[1:-1]
        
        # 2. Декодуємо JSON
        creds_info = json.loads(raw_json)
        
        # 3. ВИПРАВЛЯЄМО КЛЮЧ (саме тут зазвичай помилка JWT)
        if "private_key" in creds_info:
            # Замінюємо подвійні слеші на справжні переноси
            key = creds_info["private_key"]
            key = key.replace("\\n", "\n")
            # Видаляємо випадкові пробіли навколо ключів
            creds_info["private_key"] = key.strip()
            
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        return Credentials.from_service_account_info(creds_info, scopes=scopes)
    except Exception as e:
        logging.error(f"Помилка авторизації: {e}")
        return None
# Створюємо менеджер асинхронних з'єднань
agcm = gspread_asyncio.AsyncioGspreadClientManager(get_scoped_credentials)

async def append_to_sheet(username, number, links):
    client = await agcm.authorize()
    spreadsheet = await client.open_by_key(SPREADSHEET_ID)
    
    if username:
        ws = await spreadsheet.worksheet("TEAM")
        await ws.append_row([username, number, " | ".join(links)])
        return "TEAM"
    else:
        ws = await spreadsheet.worksheet("OFFERS")
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        await ws.append_row([now, number, " | ".join(links)])
        return "OFFERS"

# --- Логіка парсингу ---
def parse_message(text):
    words = text.split()
    number, username, tiktok_links = None, None, []
    
    for word in words:
        if "tiktok.com" in word:
            tiktok_links.append(word)
        elif word.isdigit() and number is None:
            number = int(word)
        elif "http" not in word and not word.isdigit() and username is None:
            username = word
    return username, number, tiktok_links

# --- Обробники ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "<b>NEVADA TRAFFIC | РЕГИСТРАЦИЯ ЗАЯВКИ</b>\n"
        "──────────────────────────\n"
        "Бот запущен и готов к работе ✅\n\n"
        "<b>Формат:</b>\n"
        "<code>[имя] [число] [tiktok ссылки]</code>\n\n",
        parse_mode=ParseMode.HTML
    )

@dp.message()
async def handle_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return

    logging.info(f"Отримано текст: {message.text}")
    username, number, links = parse_message(message.text)
    
    if number is None or not links:
        await message.answer("❌ <b>Ошибка:</b> Неверный формат данных.")
        return

    status_msg = await message.answer("⏳ <i>Запись данных...</i>", parse_mode=ParseMode.HTML)

    try:
        target = await append_to_sheet(username, number, links)

        res_text = (
            f"✅ <b>УСПЕШНО ЗАПИСАНО</b>\n"
            f"──────────────────────────\n"
            f"📂 <b>Раздел:</b> <code>{target}</code>\n"
            f"🔢 <b>Число:</b> <code>{number}</code>\n"
            f"🔗 <b>Ссылок:</b> <code>{len(links)}</code>\n"
            f"──────────────────────────\n"
            f"🕜 {datetime.now().strftime('%H:%M:%S')}"
        )
        await status_msg.edit_text(res_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logging.error(f"Spreadsheet error: {e}")
        await status_msg.edit_text(f"❌ <b>Ошибка записи:</b>\n{str(e)}", parse_mode=ParseMode.HTML)

async def main():
    logging.info("Бот запускається...")
    try:
        # Спробуємо запустити без видалення вебхука для тесту
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logging.error(f"Помилка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
