import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
import gspread_asyncio  # Используем асинхронную библиотеку
from google.oauth2.service_account import Credentials

load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# --- Настройка Google Sheets ---
def get_scoped_credentials():
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return creds

# Создаем менеджер асинхронных соединений
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

# --- Логика парсинга ---
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

# --- Обработчики ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "<b>NEVADA TRAFFIC | РЕГИСТРАЦИЯ ЗАЯВКИ</b>\n"
        "──────────────────────────\n"
        "Бот готов к приему ссылок ✅\n\n"
        "<b>Формат:</b>\n"
        "<code>[имя] [число] [tiktok ссылки]</code>\n\n",
        parse_mode=ParseMode.HTML
    )

@dp.message()
async def handle_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return

    username, number, links = parse_message(message.text)
    
    if number is None or not links:
        await message.answer("❌ <b>Ошибка:</b> Неверный формат. Нужно число и хотя бы одна ссылка TikTok.")
        return

    status_msg = await message.answer("⏳ <i>Запись в таблицу...</i>", parse_mode=ParseMode.HTML)

    try:
        # Вызываем асинхронную функцию записи
        target = await append_to_sheet(username, number, links)

        res_text = (
            f"✅ <b>УСПЕШНО ЗАПИСАНО</b>\n"
            f"──────────────────────────\n"
            f"📂 <b>Лист:</b> <code>{target}</code>\n"
            f"🔢 <b>Число:</b> <code>{number}</code>\n"
            f"🔗 <b>Ссылок:</b> <code>{len(links)}</code>\n"
            f"──────────────────────────\n"
            f"🕜 {datetime.now().strftime('%H:%M:%S')}"
        )
        await status_msg.edit_text(res_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logging.error(f"Spreadsheet error: {e}")
        await status_msg.edit_text("❌ <b>Ошибка доступа к таблице.</b>\nОбратитесь к администратору.")

async def main():
    logging.info("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
