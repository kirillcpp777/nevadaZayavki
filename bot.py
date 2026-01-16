from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
@@ -18,7 +18,6 @@
# ================== НАЛАШТУВАННЯ ==================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
# Виправляємо формат URL для psycopg2
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
@@ -35,9 +34,16 @@ def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, user_code TEXT UNIQUE)")
    cur.execute("CREATE TABLE IF NOT EXISTS links (number TEXT PRIMARY KEY, url TEXT)")
    # Додано is_used для відстеження вільних номерів
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            number INTEGER PRIMARY KEY, 
            url TEXT, 
            is_used BOOLEAN DEFAULT FALSE
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS trainers (trainer_id TEXT PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS issues (id SERIAL PRIMARY KEY, issue_code TEXT, user_id BIGINT, number TEXT, url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cur.execute("CREATE TABLE IF NOT EXISTS issues (id SERIAL PRIMARY KEY, issue_code TEXT, user_id BIGINT, number INTEGER, url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    cur.close()
    conn.close()
@@ -60,6 +66,28 @@ def get_or_create_user(user_id, username):
    conn.close()
    return code

def get_available_ranges():
    """Функція для красивого відображення доступних номерів (наприклад 1-10, 15, 20-25)"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT number FROM links WHERE is_used = FALSE ORDER BY number")
    nums = [row['number'] for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not nums:
        return "нет доступных номеров"

    ranges = []
    start = nums[0]
    for i in range(1, len(nums) + 1):
        if i == len(nums) or nums[i] != nums[i-1] + 1:
            end = nums[i-1]
            ranges.append(f"{start}-{end}" if start != end else f"{start}")
            if i < len(nums): start = nums[i]
    
    return ", ".join(ranges)

# ================== СТАНИ (FSM) ==================
class RegState(StatesGroup):
    waiting_for_num = State()
@@ -92,8 +120,7 @@ def admin_menu():
        ], resize_keyboard=True
    )

# ================== АДМІН: ВІДПРАВКА СТАТИ (ФОТО + КОД) ==================

# ================== АДМІН: ВІДПРАВКА СТАТИ ==================
@dp.message(F.photo, F.from_user.id.in_(ADMIN_IDS))
async def admin_quick_send_photo(message: types.Message):
    code = message.caption.strip().lower() if message.caption else None
@@ -116,59 +143,80 @@ async def admin_quick_send_photo(message: types.Message):
            await bot.send_photo(user['user_id'], message.photo[-1].file_id)
            await message.answer(f"✅ Фото відправлено коду: {code}")
        except:
            await message.answer("❌ Помилка відправки")
            await message.answer("❌ Помилка відправки (можливо юзер заблокував бота)")
    else:
        await message.answer(f"❓ Код {code} не знайдено в базі")
        await message.answer(f"❓ Код {code} не знайдено")

# ================== ХЕНДЛЕРИ КОРИСТУВАЧІВ ==================

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    user_code = get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(f"Привет! Твой код: {user_code}", reply_markup=main_menu())

@dp.message(F.text == "ПОЛУЧИТЬ ССЫЛКИ")
async def get_links(message: types.Message, state: FSMContext):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM links")
    if cur.fetchone()['count'] == 0:
        return await message.answer("❌ Ссылок нет")
async def get_links_start(message: types.Message, state: FSMContext):
    available = get_available_ranges()
    if available == "нет доступных номеров":
        return await message.answer("❌ Ссылок больше нет (все выданы).")

    stat_code = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(5))
    await state.update_data(code=stat_code)
    await message.answer("Введите номер или диапазон (например: 10 или 10-15)", reply_markup=ReplyKeyboardRemove())
    
    await message.answer(
        f"✅ <b>Доступные номера:</b> {available}\n\n"
        f"Введите номер или диапазон (например: 10 или 10-15):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegState.waiting_for_num)

@dp.message(RegState.waiting_for_num)
async def process_nums(message: types.Message, state: FSMContext):
    text = message.text.replace(" ", "")
    try:
        if "-" in text:
            a, b = map(int, text.split("-")); nums = [str(i) for i in range(min(a,b), max(a,b)+1)]
        else: nums = [text]
    except: return await message.answer("Ошибка формата")

    data = await state.get_data(); issue_code = data["code"]
    conn = get_db_connection(); cur = conn.cursor()
    msg = "<b>Ваши ссылки:</b>\n\n"; found = False
            a, b = map(int, text.split("-"))
            nums = list(range(min(a, b), max(a, b) + 1))
        else:
            nums = [int(text)]
    except:
        return await message.answer("Ошибка формата. Введите число (10) или диапазон (10-20)")

    data = await state.get_data()
    issue_code = data["code"]
    conn = get_db_connection()
    cur = conn.cursor()
    
    msg = "<b>Ваши ссылки:</b>\n\n"
    found_any = False

    for n in nums:
        cur.execute("SELECT url FROM links WHERE number = %s", (n,))
        cur.execute("SELECT url FROM links WHERE number = %s AND is_used = FALSE", (n,))
        res = cur.fetchone()
        if res:
            cur.execute("INSERT INTO issues (issue_code, user_id, number, url) VALUES (%s, %s, %s, %s)", (issue_code, message.from_user.id, n, res['url']))
            msg += f"{n}: {res['url']}\n"; found = True
            cur.execute("UPDATE links SET is_used = TRUE WHERE number = %s", (n,))
            cur.execute("INSERT INTO issues (issue_code, user_id, number, url) VALUES (%s, %s, %s, %s)", 
                        (issue_code, message.from_user.id, n, res['url']))
            msg += f"{n}: {res['url']}\n"
            found_any = True

    conn.commit(); cur.close(); conn.close()
    if not found: await message.answer("❌ Номера не найдены", reply_markup=main_menu())
    conn.commit()
    cur.close()
    conn.close()

    if not found_any:
        await message.answer("❌ Эти номера уже выданы или не существуют.", reply_markup=main_menu())
    else:
        await message.answer(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu())
        await bot.send_message(ADMIN_ID, f"✅ Выдача @{message.from_user.username}\n🔑 Код для статы: {issue_code}")
        
        # Повідомляємо що залишилось
        new_avail = get_available_ranges()
        await message.answer(f"📊 Остались свободные номера: {new_avail}")
        
    await state.clear()

# --- ФУНКЦІЯ: Я ОБУЧИЛ ЧЕЛОВЕКА ---
@dp.message(F.text == "Я обучил человека")
async def report_start(message: types.Message, state: FSMContext):
    conn = get_db_connection(); cur = conn.cursor()
@@ -189,40 +237,50 @@ async def report_finish(message: types.Message, state: FSMContext):
    await message.answer("✅ Принято", reply_markup=main_menu())
    await state.clear()

# --- ФУНКЦІЯ: СОЗДАТЬ ОБРАЩЕНИЕ ---
@dp.message(F.text == "Создать обращение")
async def support_msg(message: types.Message):
    await message.answer("Напишите ваше сообщение следующим текстом:")
    await message.answer("Просто напишите ваше сообщение боту, и админ его получит.")

@dp.message(F.chat.type == "private", ~F.from_user.id.in_(ADMIN_IDS))
async def forward_to_admin(message: types.Message):
    if message.text and not message.text.startswith("/"):
        await bot.send_message(ADMIN_ID, f"💬 ВОПРОС от @{message.from_user.username}:\n\n{message.text}")

# ================== АДМІН-ПАНЕЛЬ ==================

@dp.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: types.Message):
    await message.answer("Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "Добавить ссылки", F.from_user.id.in_(ADMIN_IDS))
async def add_links_st(message: types.Message, state: FSMContext):
    await message.answer("Формат: №10: https://...")
    await message.answer("Пришли список в формате:\n№10: https://link\n№11: https://link")
    await state.set_state(AdminState.waiting_for_links)

@dp.message(AdminState.waiting_for_links)
async def save_links(message: types.Message, state: FSMContext):
    found = re.findall(r'№(\d+):\s*(http\S+)', message.text)
    conn = get_db_connection(); cur = conn.cursor()
    count = 0
    for n, l in found:
        cur.execute("INSERT INTO links (number, url) VALUES (%s, %s) ON CONFLICT (number) DO UPDATE SET url = EXCLUDED.url", (n, l))
        cur.execute("""
            INSERT INTO links (number, url, is_used) VALUES (%s, %s, FALSE) 
            ON CONFLICT (number) DO UPDATE SET url = EXCLUDED.url, is_used = FALSE
        """, (int(n), l))
        count += 1
    conn.commit(); cur.close(); conn.close()
    await message.answer(f"✅ Добавлено: {len(found)}", reply_markup=admin_menu())
    await message.answer(f"✅ Добавлено/Обновлено: {count} ссылок", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "Очистить ссылки", F.from_user.id.in_(ADMIN_IDS))
async def clear_links(message: types.Message):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM links")
    conn.commit(); cur.close(); conn.close()
    await message.answer("🗑 Все ссылки удалены из базы.", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить ID обучающего", F.from_user.id.in_(ADMIN_IDS))
async def add_trainer(message: types.Message, state: FSMContext):
    await message.answer("Введи ID:")
    await message.answer("Введи Telegram ID пользователя:")
    await state.set_state(AdminAddTrainerState.waiting_for_id)

@dp.message(AdminAddTrainerState.waiting_for_id)
@@ -231,12 +289,15 @@ async def save_trainer(message: types.Message, state: FSMContext):
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO trainers (trainer_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.text,))
        conn.commit(); cur.close(); conn.close()
        await message.answer("✅ Добавлено", reply_markup=admin_menu())
        await message.answer("✅ Пользователь добавлен в список обучающих", reply_markup=admin_menu())
        await state.clear()
    else:
        await message.answer("ID должен состоять только из цифр.")

@dp.message(F.text == "🏠 Главное меню")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear(); await message.answer("Меню:", reply_markup=main_menu())
    await state.clear()
    await message.answer("Вы вернулись в меню:", reply_markup=main_menu())

async def main():
