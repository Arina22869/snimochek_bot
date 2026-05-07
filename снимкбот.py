import asyncio
import random
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.enums import ParseMode

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8772848542:AAG1IXVDw6MMAGtjyVjh8Mm068q5VnWeteM"  # ← ВСТАВЬТЕ СВОЙ ТОКЕН

# Вопросы для знакомства
QUESTIONS = [
    "Какая последняя песня, которую ты слушал?",
    "Какой фильм посоветуешь посмотреть?",
    "Кофе или чай?",
    "Ты жаворонок или сова?",
    "Какое у тебя хобби?",
    "Что бы ты взял на необитаемый остров?",
    "Какая самая глупая покупка в твоей жизни?",
    "Если бы ты был супергероем, какая сила у тебя была бы?",
    "Какое место мечтаешь посетить?",
    "Что тебя бесит в учёбе, а что радует?",
]

# ===== БАЗА ДАННЫХ =====
conn = sqlite3.connect("game_bot.db")
c = conn.cursor()

# Таблица пользователей
c.execute("""CREATE TABLE IF NOT EXISTS users 
             (user_id INTEGER PRIMARY KEY, 
              username TEXT, 
              points INTEGER DEFAULT 0)""")

# Таблица выполненных пар (чтобы не повторялись в один день)
c.execute("""CREATE TABLE IF NOT EXISTS pairs 
             (user_id INTEGER, 
              partner_id INTEGER, 
              date TEXT)""")

# Таблица королей чата
c.execute("""CREATE TABLE IF NOT EXISTS kings 
             (user_id INTEGER, 
              date TEXT)""")

# Таблица помощников старосты
c.execute("""CREATE TABLE IF NOT EXISTS helpers 
             (user_id INTEGER, 
              date TEXT)""")

conn.commit()

# ===== ИНИЦИАЛИЗАЦИЯ БОТА =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def get_random_partner(user_id):
    """Выбирает случайного партнёра, с которым ещё не было пары сегодня"""
    today = datetime.now().date().isoformat()
    c.execute("SELECT partner_id FROM pairs WHERE user_id = ? AND date = ?", (user_id, today))
    today_pairs = [row[0] for row in c.fetchall()]
    
    c.execute("SELECT user_id FROM users WHERE user_id != ?", (user_id,))
    all_users = [row[0] for row in c.fetchall()]
    
    available = [uid for uid in all_users if uid not in today_pairs]
    if not available:
        return None
    return random.choice(available)

def get_username_by_id(user_id):
    c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    return row[0] if row else str(user_id)

# ===== КОМАНДЫ ДЛЯ ЛИЧНОЙ ПЕРЕПИСКИ =====

@dp.message(Command("start"))
async def start_game(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    # Регистрация пользователя
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    
    partner_id = get_random_partner(user_id)
    if not partner_id:
        await message.answer("❌ Сегодня ты уже со всеми познакомился! Возвращайся завтра 🎉")
        return
    
    partner_name = get_username_by_id(partner_id)
    question = random.choice(QUESTIONS)
    
    # Сохраняем пару
    today = datetime.now().date().isoformat()
    c.execute("INSERT INTO pairs (user_id, partner_id, date) VALUES (?, ?, ?)", 
              (user_id, partner_id, today))
    conn.commit()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнил!", callback_data=f"done_{partner_id}")]
    ])
    
    await message.answer(
        f"🎲 *Твоя миссия:*\n\n"
        f"Найди человека с ником @{partner_name}\n\n"
        f"Задай ему вопрос:\n"
        f"❓ _{question}_\n\n"
        f"Когда спросишь — нажми кнопку 👇",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query(lambda c: c.data and c.data.startswith("done_"))
async def done_pair(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    partner_id = int(callback.data.split("_")[1])
    
    # Начисляем очки
    c.execute("UPDATE users SET points = points + 10 WHERE user_id = ?", (user_id,))
    c.execute("UPDATE users SET points = points + 5 WHERE user_id = ?", (partner_id,))
    conn.commit()
    
    await callback.message.edit_text(
        "✅ *Молодец!*\n\n"
        "➕ +10 очков тебе\n"
        "➕ +5 очков твоему собеседнику\n\n"
        "Продолжай знакомиться! 🎉"
    )
    await callback.answer()

# ===== КОМАНДЫ ДЛЯ ГРУППОВОГО ЧАТА =====

@dp.message(Command("help"))
async def show_help(message: types.Message):
    if message.chat.type == "private":
        help_text = """
🤖 *Мой функционал для тебя лично:*

/start — начать игру на знакомство
/help — показать эту памятку

🎮 *Как играть:*
1. Напиши /start
2. Я дам тебе случайного собеседника и вопрос
3. Найди его в общем чате и задай вопрос
4. Нажми «Выполнил!» и получи очки

📊 *Очки нужны, чтобы:*
- Стать королём чата
- Помогать старосте
- Попасть в топ активных
"""
    else:
        help_text = """
👋 *Команды для общего чата:*

/king 👑 — выбрать короля чата на сегодня
/helper 🛠️ — выбрать помощника старосты
/roll 🎲 — случайное число 1–100
/top 🏆 — топ активных участников
/poll «вопрос» «вариант1» «вариант2» — быстрый опрос
/game 🎭 — сыграть в крокодила
/commands — список всех команд

🧑‍🎓 *Для знакомства в личку:*
Напиши мне в личные сообщения и используй /start

📌 *Король чата* может помогать старосте и запускать игры.
🛠️ *Помощник старосты* — правая рука в организации.
"""
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("commands"))
async def show_commands(message: types.Message):
    text = """
📋 *Доступные команды:*

/help — полная памятка
/king — король чата 👑
/helper — помощник старосты 🛠️
/roll — случайное число 🎲
/top — топ игроков 🏆
/poll — создать опрос
/game — крокодил 🎭
"""
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("king"))
async def choose_king(message: types.Message):
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в общем чате группы!")
        return
    
    today = datetime.now().date().isoformat()
    c.execute("SELECT user_id FROM kings WHERE date = ?", (today,))
    if c.fetchone():
        await message.answer("👑 Король на сегодня уже выбран! Завтра будет новый.")
        return
    
    c.execute("SELECT user_id, username FROM users ORDER BY RANDOM() LIMIT 1")
    user = c.fetchone()
    if not user:
        await message.answer("Сначала кто-нибудь напиши /start в личку боту, чтобы я вас запомнил!")
        return
    
    user_id, username = user
    c.execute("INSERT INTO kings (user_id, date) VALUES (?, ?)", (user_id, today))
    c.execute("UPDATE users SET points = points + 50 WHERE user_id = ?", (user_id,))
    conn.commit()
    
    await message.answer(f"👑 *Новый король чата — @{username}!*\n+50 очков! 🎉", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("helper"))
async def choose_helper(message: types.Message):
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в общем чате группы!")
        return
    
    today = datetime.now().date().isoformat()
    c.execute("SELECT user_id FROM helpers WHERE date = ?", (today,))
    if c.fetchone():
        await message.answer("🛠️ Помощник старосты на сегодня уже выбран!")
        return
    
    c.execute("SELECT user_id, username FROM users ORDER BY RANDOM() LIMIT 1")
    user = c.fetchone()
    if not user:
        await message.answer("Сначала кто-нибудь напиши /start в личку боту!")
        return
    
    user_id, username = user
    c.execute("INSERT INTO helpers (user_id, date) VALUES (?, ?)", (user_id, today))
    c.execute("UPDATE users SET points = points + 30 WHERE user_id = ?", (user_id,))
    conn.commit()
    
    await message.answer(f"🛠️ *Помощник старосты на сегодня — @{username}!*\n+30 очков! 🙌", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("roll"))
async def roll_dice(message: types.Message):
    number = random.randint(1, 100)
    user = message.from_user.first_name
    await message.answer(f"🎲 *{user}* выбросил(а) число **{number}**", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("top"))
async def show_top(message: types.Message):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 5")
    top_users = c.fetchall()
    
    if not top_users:
        await message.answer("Пока нет участников. Напиши /start в личку боту, чтобы попасть в таблицу!")
        return
    
    text = "🏆 *Топ активных участников:*\n\n"
    for i, (username, points) in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        text += f"{medal} @{username} — {points} очков\n"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("poll"))
async def create_poll(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📊 *Как создать опрос:*\n/poll «Вопрос» «Вариант1» «Вариант2» «Вариант3»\n\nПример:\n/poll «Любимый предмет?» «Матан» «Программирование»", parse_mode=ParseMode.MARKDOWN)
        return
    
    parts = args[1].split('"')
    question = None
    options = []
    
    for p in parts:
        p = p.strip()
        if p and question is None:
            question = p
        elif p and len(options) < 10:
            options.append(p)
    
    if not question or len(options) < 2:
        await message.answer("Нужен вопрос и минимум 2 варианта.\nПример:\n/poll «Любимый предмет?» «Матан» «Программирование»")
        return
    
    await message.answer_poll(question=question, options=options, is_anonymous=False)

@dp.message(Command("game"))
async def play_crocodile(message: types.Message):
    words = [
        ("📚 Экзамен", "университет"),
        ("☕ Кофе", "еда"),
        ("😴 Пара", "университет"),
        ("🎓 Стипендия", "университет"),
        ("🏋️ Спортзал", "место"),
        ("🍕 Пицца", "еда"),
        ("📱 ТикТок", "приложение"),
        ("🐱 Кот", "животное"),
    ]
    word, category = random.choice(words)
    
    await message.answer(
        f"🎭 *Игра Крокодил!*\n\n"
        f"Категория: *{category}*\n"
        f"Загаданное слово: ||{word}||\n\n"
        f"Задача: объяснить слово без звуков и жестов? А, нет 🤪\n"
        f"В крокодила играем вживую! А пока — вот тебе слово для разминки.",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.my_chat_member()
async def bot_added_to_group(update: ChatMemberUpdated):
    if update.new_chat_member.status == "member":
        welcome_text = """
🎉 *Всем привет! Я бот-координатор* 🎉

Я здесь, чтобы помочь вам знакомиться и развлекаться.

📌 *Что я умею:*

👑 `/king` — выбрать короля чата
🛠️ `/helper` — выбрать помощника старосты
🎲 `/roll` — случайное число
🏆 `/top` — топ активных
🎭 `/game` — крокодил

🧑‍🎓 *Чтобы начать игру на знакомство:*
Напишите мне в ЛИЧНЫЕ СООБЩЕНИЯ и используйте `/start`

Полную памятку смотри по команде `/help`

Приятного общения! 💬
"""
        await update.bot.send_message(
            chat_id=update.chat.id,
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )

# ===== ЗАПУСК БОТА =====
async def main():
    print("🤖 Бот запущен и работает...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
