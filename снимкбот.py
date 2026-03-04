import logging
import sqlite3
import random
from contextlib import contextmanager
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio

# ============= Google Sheets API =============
import gspread
from google.oauth2.service_account import Credentials
# =============================================

# ============= НАСТРОЙКИ =============
TOKEN = "8539041735:AAEPU2_9wus9Tv82jDEVcj213kvnsxNMU2s"
ADMIN_IDS = [1665864236]

# ID твоей таблицы (из ссылки)
SPREADSHEET_ID = "1oMohwWx3xIEt9N_s9NXMAerKM4JReqVLozadPC52ZJA"
# =====================================

# ============= Смайлики для предметов =============
ITEM_EMOJIS = {
    "кепка": "🧢",
    "носки": "🧦",
    "кружка": "☕",
    "брелок": "🔑",
    "стикеры": "🎨",
    "снимочков": "🪙",
    "снимочки": "🪙",
    "ТЗ": "⏰",
    "статус": "📝",
    "опоздать": "⏳",
    "бонусный сундук": "🎁",
    "фото": "📸",
    "фриспин": "🎰",
    "музыку": "🎵",
    "джекпот": "💎",
}
# =====================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ============= Google Sheets подключение =============
def get_gs_client():
    try:
        creds = Credentials.from_service_account_file(
            'google_key.json',
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None

def get_users_sheet():
    client = get_gs_client()
    if not client:
        return None
    try:
        return client.open_by_key(SPREADSHEET_ID).worksheet("users")
    except Exception as e:
        logging.error(f"❌ Ошибка получения листа users: {e}")
        return None

# ============= Работа с пользователями =============
def get_user_row(user_id):
    """Возвращает номер строки пользователя или None"""
    sheet = get_users_sheet()
    if not sheet:
        return None
    
    try:
        all_rows = sheet.get_all_values()
        user_id_str = str(user_id)
        for i, row in enumerate(all_rows, start=1):
            if row and row[0] == user_id_str:
                return i
        return None
    except Exception as e:
        logging.error(f"Ошибка поиска пользователя: {e}")
        return None

def get_user_snimochki(user_id):
    """Читает снимочки из таблицы"""
    sheet = get_users_sheet()
    if not sheet:
        return 0
    
    try:
        row_num = get_user_row(user_id)
        if row_num:
            val = sheet.cell(row_num, 4).value  # колонка D
            return int(val) if val and val.lstrip('-').isdigit() else 0
        return 0
    except Exception as e:
        logging.error(f"Ошибка чтения снимочков: {e}")
        return 0

def update_user_snimochki(user_id, new_value):
    """Обновляет снимочки пользователя"""
    sheet = get_users_sheet()
    if not sheet:
        return False
    
    try:
        row_num = get_user_row(user_id)
        if row_num:
            sheet.update_cell(row_num, 4, str(new_value))
            return True
        else:
            # Если пользователя нет в таблице — создаём
            name = f"User{user_id}"  # временное имя
            sheet.append_row([str(user_id), name, "0", str(new_value), ""])
            return True
    except Exception as e:
        logging.error(f"Ошибка обновления снимочков: {e}")
        return False

# ============= SQLite (инвентарь) =============
@contextmanager
def get_db():
    conn = sqlite3.connect('inventory.db')
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER PRIMARY KEY,
                items TEXT
            )
        ''')
        conn.commit()

def get_inventory(user_id):
    with get_db() as conn:
        cursor = conn.execute("SELECT items FROM inventory WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        return ""

def update_inventory(user_id, items_dict):
    items_str = ",".join([f"{name}:{count}" for name, count in items_dict.items()])
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO inventory (user_id, items) VALUES (?, ?)",
            (user_id, items_str)
        )
        conn.commit()

def parse_inventory(items_str):
    if not items_str:
        return {}
    result = {}
    for item in items_str.split(','):
        if ':' in item:
            name, count = item.split(':')
            result[name] = int(count)
    return result

def add_to_inventory(user_id, item_name, count=1):
    items_dict = parse_inventory(get_inventory(user_id))
    items_dict[item_name] = items_dict.get(item_name, 0) + count
    update_inventory(user_id, items_dict)

def remove_from_inventory(user_id, item_name, count=1):
    items_dict = parse_inventory(get_inventory(user_id))
    if item_name in items_dict and items_dict[item_name] >= count:
        items_dict[item_name] -= count
        if items_dict[item_name] <= 0:
            del items_dict[item_name]
        update_inventory(user_id, items_dict)
        return True
    return False

def has_item(user_id, item_name):
    items_dict = parse_inventory(get_inventory(user_id))
    return item_name in items_dict and items_dict[item_name] > 0

def get_item_emoji(item_name):
    """Возвращает эмодзи для предмета"""
    for key, emoji in ITEM_EMOJIS.items():
        if key in item_name.lower():
            return emoji
    return "📦"  # эмодзи по умолчанию

# ============= Игровая логика =============
def open_chest():
    items = [
        {"name": "кепка \"СНИМК\"", "rarity": "обычный"},
        {"name": "носки \"СНИМК\"", "rarity": "обычный"},
        {"name": "кружка \"СНИМК\"", "rarity": "обычный"},
        {"name": "брелок \"СНИМК\"", "rarity": "обычный"},
        {"name": "стикеры \"СНИМК\"", "rarity": "обычный"},
        {"name": "5 снимочков", "rarity": "редкий"},
        {"name": "10 снимочков", "rarity": "редкий"},
        {"name": "просрочить ТЗ на 2 часа", "rarity": "редкий"},
        {"name": "поменять статус в чате", "rarity": "редкий"},
        {"name": "легально опоздать", "rarity": "редкий"},
        {"name": "15 снимочков", "rarity": "очень редкий"},
        {"name": "бонусный сундук", "rarity": "очень редкий"},
        {"name": "фото с председателем", "rarity": "очень редкий"},
        {"name": "один фриспин", "rarity": "очень редкий"},
        {"name": "два фриспина", "rarity": "легендарный"},
        {"name": "право выбрать музыку", "rarity": "легендарный"},
        {"name": "20 снимочков", "rarity": "легендарный"},
    ]
    
    rarity_chances = {
        "обычный": 0.5,
        "редкий": 0.3,
        "очень редкий": 0.15,
        "легендарный": 0.05
    }
    
    rarity_groups = {}
    for item in items:
        if item["rarity"] not in rarity_groups:
            rarity_groups[item["rarity"]] = []
        rarity_groups[item["rarity"]].append(item)
    
    rand = random.random()
    cumulative = 0
    selected_rarity = "обычный"
    for rarity, chance in rarity_chances.items():
        cumulative += chance
        if rand < cumulative:
            selected_rarity = rarity
            break
    
    if selected_rarity in rarity_groups:
        return random.choice(rarity_groups[selected_rarity])
    return None

def spin_wheel():
    rand = random.randint(1, 100)
    if rand <= 50:
        return {"type": "snimochki", "value": 5, "name": "+5 снимочков"}
    elif rand <= 65:
        return {"type": "item", "value": "кепка \"СНИМК\"", "name": "кепка \"СНИМК\""}
    elif rand <= 75:
        return {"type": "snimochki", "value": 10, "name": "+10 снимочков"}
    elif rand <= 85:
        return {"type": "nothing", "value": 0, "name": "ничего"}
    elif rand <= 90:
        return {"type": "item", "value": "5 снимочков", "name": "5 снимочков (бонус)"}
    elif rand <= 95:
        return {"type": "snimochki", "value": 15, "name": "+15 снимочков"}
    elif rand <= 99:
        return {"type": "item", "value": "бонусный сундук", "name": "бонусный сундук"}
    else:
        return {"type": "jackpot", "value": 50, "name": "ДЖЕКПОТ! +50 снимочков"}

# ============= Клавиатуры =============
def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎁 Открыть сундук (5)", callback_data="open_chest"),
        InlineKeyboardButton(text="🎲 Испытать удачу (3)", callback_data="spin")
    )
    builder.row(
        InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
        InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory")
    )
    return builder.as_markup()

def back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu"))
    return builder.as_markup()

def chest_result_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎁 Ещё сундук", callback_data="open_chest"),
        InlineKeyboardButton(text="🎲 Ещё удачу", callback_data="spin")
    )
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu"))
    return builder.as_markup()

# ============= Команды =============
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    snimochki = get_user_snimochki(user_id)
    
    await message.answer(
        f"👋 Привет, {name}!\n\n"
        f"🪙 Твои снимочки: {snimochki}\n\n"
        "🎮 Выбери действие:",
        reply_markup=main_menu_keyboard()
    )

@dp.callback_query(lambda c: c.data == "menu")
async def back_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    name = callback.from_user.full_name
    snimochki = get_user_snimochki(user_id)
    
    await callback.message.edit_text(
        f"👋 Привет, {name}!\n\n"
        f"🪙 Твои снимочки: {snimochki}\n\n"
        "🎮 Выбери действие:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    name = callback.from_user.full_name
    snimochki = get_user_snimochki(user_id)
    
    items_dict = parse_inventory(get_inventory(user_id))
    inventory_text = ""
    if items_dict:
        inventory_lines = []
        for item, count in items_dict.items():
            emoji = get_item_emoji(item)
            inventory_lines.append(f"• {emoji} {item} ×{count}")
        inventory_text = "\n".join(inventory_lines)
    else:
        inventory_text = "пусто"
    
    await callback.message.edit_text(
        f"👤 **{name}**\n"
        f"🪙 Снимочки: {snimochki}\n\n"
        f"🎒 **Инвентарь:**\n{inventory_text}",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "inventory")
async def show_inventory(callback: CallbackQuery):
    user_id = callback.from_user.id
    items_dict = parse_inventory(get_inventory(user_id))
    
    if items_dict:
        inventory_lines = []
        for item, count in items_dict.items():
            emoji = get_item_emoji(item)
            inventory_lines.append(f"• {emoji} {item} ×{count}")
        inventory_text = "\n".join(inventory_lines)
    else:
        inventory_text = "пусто"
    
    await callback.message.edit_text(
        f"🎒 **Твой инвентарь:**\n{inventory_text}",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "open_chest")
async def open_chest_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    snimochki = get_user_snimochki(user_id)
    
    if snimochki < 5:
        await callback.message.edit_text(
            "❌ Недостаточно снимочков! Сундук стоит 5 снимочков.",
            reply_markup=back_keyboard()
        )
        await callback.answer()
        return
    
    item = open_chest()
    if item:
        # Списываем 5 снимочков
        update_user_snimochki(user_id, snimochki - 5)
        add_to_inventory(user_id, item["name"])
        
        emoji = get_item_emoji(item["name"])
        
        await callback.message.edit_text(
            f"🎁 Ты открываешь сундук...\n\n"
            f"✨ Выпало: {emoji} {item['name']}\n\n"
            f"🪙 Списано 5 снимочков\n"
            f"💰 Новый баланс: {snimochki - 5}\n"
            f"🎒 {emoji} {item['name']} добавлен в инвентарь!",
            reply_markup=chest_result_keyboard()
        )
    else:
        await callback.message.edit_text("❌ Ошибка", reply_markup=back_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "spin")
async def spin_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    snimochki = get_user_snimochki(user_id)
    has_freespin = has_item(user_id, "один фриспин")
    
    if not has_freespin and snimochki < 3:
        await callback.message.edit_text(
            "❌ Недостаточно снимочков! Испытание удачи стоит 3 снимочка.",
            reply_markup=back_keyboard()
        )
        await callback.answer()
        return
    
    result = spin_wheel()
    new_snimochki = snimochki
    reward_text = ""
    
    # Обработка результата
    if result["type"] == "snimochki":
        new_snimochki += result["value"]
        emoji = get_item_emoji("снимочки")
        reward_text = f"🎉 Ты выиграл: {emoji} {result['name']}!"
    elif result["type"] == "jackpot":
        new_snimochki += result["value"]
        emoji = get_item_emoji("джекпот")
        reward_text = f"{emoji} ДЖЕКПОТ! {result['name']}!"
    elif result["type"] == "item":
        add_to_inventory(user_id, result["value"])
        emoji = get_item_emoji(result["value"])
        reward_text = f"🎉 Ты получил: {emoji} {result['name']}!"
    else:
        reward_text = "😢 В этот раз не повезло. Попробуй ещё!"
    
    # Списываем ресурсы
    if has_freespin:
        remove_from_inventory(user_id, "один фриспин")
        cost_text = "🎰 Использован фриспин!"
    else:
        new_snimochki -= 3
        cost_text = "🪙 Потрачено 3 снимочка"
    
    # Обновляем баланс в таблице
    update_user_snimochki(user_id, new_snimochki)
    
    await callback.message.edit_text(
        f"🎲 Ты бросаешь кубик...\n\n"
        f"{reward_text}\n\n"
        f"{cost_text}\n"
        f"💰 Новый баланс: {new_snimochki}",
        reply_markup=chest_result_keyboard()
    )
    await callback.answer()

# ============= Запуск =============
async def main():
    init_db()
    print("🚀 Бот СНИМочки (API версия) запущен! Нажми Ctrl+C для остановки.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
