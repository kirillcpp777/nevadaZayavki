import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Загрузка переменных из .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def get_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)

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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "<b>NEVADA TRAFFIC | Logging System</b>\n"
        "──────────────────────────\n"
        "Система регистрации трафика запущена.\n\n"
        "<b>Формат отчета:</b>\n"
        "<code>[имя] [число] [ссылки]</code>\n\n"
        "Отправьте данные для автоматической записи в Google Sheets."
    )
    await message.answer(welcome_text, parse_mode=ParseMode.HTML)

@dp.message()
async def handle_message(message: types.Message):
    username, number, links = parse_message(message.text)
    
    if number is None or not links:
        await message.answer("❌ <b>Ошибка:</b> Неверный формат данных.", parse_mode=ParseMode.HTML)
        return

    status_msg = await message.answer("⏳ <i>Запись данных...</i>", parse_mode=ParseMode.HTML)

    try:
        sheet = get_spreadsheet()
        if username:
            ws = sheet.worksheet("TEAM")
            ws.append_row([username, number, " | ".join(links)])
            target = "TEAM"
        else:
            ws = sheet.worksheet("OFFERS")
            now = datetime.now().strftime("%d.%m.%Y %H:%M")
            ws.append_row([now, number, " | ".join(links)])
            target = "OFFERS"

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
        logging.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ <b>Ошибка записи:</b>\n<code>{str(e)}</code>", parse_mode=ParseMode.HTML)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())