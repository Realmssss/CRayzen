import telebot
from telebot import types
import sqlite3
import random
import datetime
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8766706568:AAHlUlZqYWQq9DvIJYoF0wIb3fu3gHJld74'
ORGANIZER_USERNAME = 'Kitenokowo13'
ORGANIZER_ID = None
TEST_MODE_USER = 'angel_zam'
bot = telebot.TeleBot(BOT_TOKEN)

# Планировщик
scheduler = BackgroundScheduler()
scheduler.start()

# Хранилища
active_games = {}
boss_battles = {}
user_ids = {}
scheduled_jobs = {}
card_selections = {}
notification_settings = {}

# --- ФУНКЦИЯ ЭКРАНИРОВАНИЯ HTML ---
def escape_html(text):
    if text is None:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        nickname TEXT,
        coins INTEGER DEFAULT 0,
        battles_today INTEGER DEFAULT 0,
        last_play_date TEXT,
        is_test_mode INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        file_id TEXT,
        card_name TEXT,
        uploaded_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        file_id TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS scheduled_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        message_text TEXT,
        notify_text TEXT,
        schedule_time TEXT,
        notify_before INTEGER,
        created_by INTEGER
    )''')
    
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        locations_data = [
            ('ГОРЫ СЕВЕРА', 'Если показатель скорости одной карты равен показателю другой, каждая из них может промахнуться с вероятностью 1d4', None),
            ('ЮЖНЫЕ ПОЛЯ', 'Атака противника -1, если вы используете поддержку', None),
            ('Город', 'Вашу карту невозможно убить за один удар (удар что должен был вас убить оставляет вам 1 защиту)', None),
            ('Арена', 'Если защита карты уменьшается от активных способностей она так же теряет и одну скорость', None),
            ('ЧИСТИЛИЩЕ', 'Разница между скоростью карт означает число дополнительных бросков кубика у поддержки', None),
            ('ЭЛЬФИЙСКИЙ ЛЕС', 'Карты у которых тактика = 0, не могут использовать активные способности', None),
            ('Таверна', 'Поддержка имеет двойной эффект', None),
            ('ВЕЛИКАЯ ПУСТОШЬ', 'В начале КАЖДОГО раунда карты получают 1 урон', None)
        ]
        c.executemany("INSERT INTO locations (name, description, file_id) VALUES (?, ?, ?)", locations_data)
    
    conn.commit()
    conn.close()

def setup_bot_commands():
    """Настройка команд ТОЛЬКО для ЛС (без /r и /s)"""
    
    private_commands = [
        types.BotCommand('start', '🚀 Запустить бота'),
        types.BotCommand('name', '👤 Установить прозвище'),
        types.BotCommand('add', '🃏 Загрузить карту'),
        types.BotCommand('my_cards', '📚 Мои карты'),
        types.BotCommand('locations', '📍 Список локаций'),
        types.BotCommand('delete', '🗑️ Удалить карту'),
        types.BotCommand('surrender', '🏳️ Сдаться')
    ]
    
    bot.set_my_commands(private_commands, types.BotCommandScopeDefault())
    
    print("✅ Команды для ЛС настроены!")
    print("⚠️ /r и /s НЕ будут видны в ЛС")
    print("⚠️ Для групп отправьте: /setup_group_commands")

def get_user(user_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user = (user_id, None, None, 0, 0, None, 0)
    conn.close()
    return user

def update_user(user_id, **kwargs):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    for key, value in kwargs.items():
        c.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def get_user_cards(user_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, file_id, card_name FROM cards WHERE user_id = ?", (user_id,))
    cards = c.fetchall()
    conn.close()
    return cards

def get_card_by_id(card_id, user_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, file_id, card_name FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))
    card = c.fetchone()
    conn.close()
    return card

def add_card(user_id, file_id, card_name):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO cards (user_id, file_id, card_name, uploaded_date) VALUES (?, ?, ?, ?)",
              (user_id, file_id, card_name, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()

def delete_card(card_id, user_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT file_id, card_name FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))
    card = c.fetchone()
    if card:
        c.execute("DELETE FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))
        conn.commit()
    conn.close()
    return card

def get_locations():
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, name, description, file_id FROM locations")
    locs = c.fetchall()
    conn.close()
    return locs

def check_limits(user_id):
    user = get_user(user_id)
    today = datetime.date.today()
    if user[5] != today.isoformat():
        return True, 7 if today.weekday() != 5 else 14
    
    limit = 7 if today.weekday() != 5 else 14
    if user[4] < limit:
        return True, limit - user[4]
    return False, 0

def update_user_stats(user_id, coins_change, battle_played):
    user = get_user(user_id)
    today = datetime.date.today().isoformat()
    
    current_coins = user[3]
    current_battles = user[4]
    last_date = user[5]
    
    if last_date != today:
        current_battles = 0
    
    if battle_played:
        current_battles += 1
    
    new_coins = current_coins + coins_change
    
    update_user(user_id, coins=new_coins, 
                battles_today=current_battles, last_play_date=today)
    
    return new_coins, current_battles

def is_monday():
    return datetime.datetime.today().weekday() == 0

def is_friday():
    return datetime.datetime.today().weekday() == 4

def is_sunday():
    return datetime.datetime.today().weekday() == 6
# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start', 'get_id'])
def send_welcome(message):
    global ORGANIZER_ID
    user_id = message.from_user.id
    username = message.from_user.username
    
    if username:
        user_ids[username] = user_id
    
    if username == ORGANIZER_USERNAME:
        ORGANIZER_ID = user_id
        update_user(user_id, username=username)
        bot.send_message(user_id, "✅ Вы зарегистрированы как ОРГАНИЗАТОР системы!")
    
    user = get_user(user_id)
    update_user(user_id, username=username)
    
    first_name = escape_html(message.from_user.first_name)
    nickname = escape_html(user[2] if user[2] else 'Не установлено')
    
    text = (f"🎮 <b>Привет, {first_name}!</b>\n\n"
            f"💰 Монеты: {user[3]}\n"
            f"⚔️ Боёв сегодня: {user[4]}/7 (14 в субботу)\n"
            f"👤 Прозвище: {nickname}\n\n"
            f"<b>📋 КОМАНДЫ:</b>\n"
            f"🔹 /stats — Моя статистика\n"
            f"🔹 /name — Установить прозвище\n"
            f"🔹 /add — Загрузить карту (ответьте на фото)\n"
            f"🔹 /my_cards — Моя колода (с картинками)\n"
            f"🔹 /delete — Удалить карту\n"
            f"🔹 /surrender — Сдаться в бою\n"
            f"🔹 /locations — Список локаций")
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    user = get_user(message.from_user.id)
    today = datetime.date.today()
    limit = 14 if today.weekday() == 5 else 7
    battles = user[4] if user[5] == today.isoformat() else 0
    
    nickname = escape_html(user[2] if user[2] else 'Не установлено')
    
    text = (f"📊 <b>Статистика</b>\n"
            f"💰 Монеты: {user[3]}\n"
            f"⚔️ Боёв сегодня: {battles}/{limit}\n"
            f"📅 Осталось боев: {limit - battles}\n"
            f"👤 Прозвище: {nickname}")
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['stats_user'])
def stats_user(message):
    global ORGANIZER_ID
    user_id = message.from_user.id
    
    if ORGANIZER_ID and user_id != ORGANIZER_ID:
        bot.reply_to(message, "❌ Только организатор может использовать эту команду!")
        return
    
    try:
        target_id = int(message.text.split()[1])
        target = get_user(target_id)
        
        today = datetime.date.today()
        limit = 14 if today.weekday() == 5 else 7
        battles = target[4] if target[5] == today.isoformat() else 0
        
        nickname = escape_html(target[2] if target[2] else 'Не установлено')
        username = escape_html(target[1] if target[1] else 'Нет')
        
        text = (f"📊 <b>Статистика игрока</b>\n\n"
                f"👤 ID: <code>{target_id}</code>\n"
                f"📛 Username: @{username}\n"
                f"🏷️ Прозвище: {nickname}\n"
                f"💰 Монеты: {target[3]}\n"
                f"⚔️ Боёв сегодня: {battles}/{limit}\n"
                f"📅 Осталось боев: {limit - battles}")
        
        bot.reply_to(message, text, parse_mode="HTML")
    except (IndexError, ValueError):
        bot.reply_to(message, "Использование: /stats_user <user_id>")

@bot.message_handler(commands=['name'])
def set_nickname_short(message):
    try:
        nickname = message.text.split(' ', 1)[1].strip()
        if len(nickname) > 20:
            bot.reply_to(message, "Прозвище слишком длинное (макс. 20 символов)")
            return
        update_user(message.from_user.id, nickname=nickname)
        bot.reply_to(message, f"✅ Прозвище установлено: {nickname}")
    except IndexError:
        bot.reply_to(message, "Использование: /name <прозвище>")

@bot.message_handler(commands=['add'])
def upload_card_short(message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "Ответьте на фото карты этой командой")
        return
    
    try:
        card_name = message.text.split(' ', 1)[1].strip()
    except IndexError:
        bot.reply_to(message, "Укажите название карты: /add <название>")
        return
    
    file_id = message.reply_to_message.photo[-1].file_id
    add_card(message.from_user.id, file_id, card_name)
    bot.reply_to(message, f"✅ Карта '{card_name}' загружена!")

@bot.message_handler(commands=['my_cards'])
def my_cards(message):
    user_id = message.from_user.id
    cards = get_user_cards(user_id)
    
    if not cards:
        bot.reply_to(message, "У вас нет загруженных карт")
        return
    
    for idx, (card_id, file_id, name) in enumerate(cards, 1):
        caption = f"🃏 <b>Карта #{idx}</b>\n"
        caption += f"ID: <code>{card_id}</code>\n"
        caption += f"Название: {escape_html(name)}"
        
        bot.send_photo(user_id, file_id, caption=caption, parse_mode="HTML")
    
    bot.send_message(user_id, 
        f"📇 <b>Всего карт в колоде: {len(cards)}</b>\n\n"
        f"💡 <b>Как использовать в бою:</b>\n"
        f"1️⃣ Напишите номера карт через запятую\n"
        f"2️⃣ Поставьте двоеточие\n"
        f"3️⃣ Напишите способности через запятую\n\n"
        f"<b>Пример:</b> <code>1,2,3: 2,0,1</code>\n"
        f"Бот автоматически отправит картинки карт!", 
        parse_mode="HTML")

@bot.message_handler(commands=['delete'])
def delete_card_short(message):
    try:
        card_id = int(message.text.split()[1])
        card = delete_card(card_id, message.from_user.id)
        if card:
            file_id, card_name = card
            for chat_id, game in active_games.items():
                if message.from_user.id in [game.get('p1'), game.get('p2')]:
                    bot.send_message(chat_id, 
                        f"⚠️ Игрок {escape_html(message.from_user.first_name)} удалил карту '{escape_html(card_name)}'")
                    bot.send_photo(chat_id, file_id)
            bot.reply_to(message, f"✅ Карта '{escape_html(card_name)}' удалена")
        else:
            bot.reply_to(message, "Карта не найдена")
    except (IndexError, ValueError):
        bot.reply_to(message, "Использование: /delete <ID>")

@bot.message_handler(commands=['surrender'])
def surrender(message):
    user_id = message.from_user.id
    for chat_id, game in list(active_games.items()):
        if user_id in [game.get('p1'), game.get('p2')]:
            p2_name = game['nickname_p2'] if game['nickname_p2'] else "Ведущий"
            bot.send_message(chat_id, 
                f"⚠️ {escape_html(game['nickname_p1'] if user_id == game['p1'] else p2_name)} сдался!")
            
            winner_id = game['p2'] if user_id == game['p1'] else game['p1']
            winner_nick = game['nickname_p2'] if user_id == game['p1'] else game['nickname_p1']
            
            w_total, w_rem = update_user_stats(winner_id, 3, True)
            l_total, l_rem = update_user_stats(user_id, 0, True)
            
            today = datetime.date.today()
            limit = 14 if today.weekday() == 5 else 7
            
            bot.send_message(chat_id, 
                f"🏆 {escape_html(winner_nick or 'Ведущий')} побеждает!\n"
                f"💰 +3 монеты (Всего: {w_total}, Осталось боев: {w_rem}/{limit})", 
                parse_mode="HTML")
            del active_games[chat_id]
            return
    
    bot.reply_to(message, "Вы не участвуете в активной игре")

@bot.message_handler(commands=['locations'])
def show_locations(message):
    locations = get_locations()
    if not locations:
        bot.reply_to(message, "Локации не загружены")
        return
    
    text = "📍 <b>Доступные локации:</b>\n\n"
    for loc_id, name, desc, _ in locations:
        text += f"<b>{escape_html(name)}</b>\n{escape_html(desc)}\n\n"
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['notifications'])
def notifications_settings(message):
    username = message.from_user.username
    user_id = message.from_user.id
    
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "Доступ запрещён")
        return
    
    markup = types.InlineKeyboardMarkup()
    
    current_setting = notification_settings.get(user_id, False)
    btn_text = "🔔 Включить уведомления" if not current_setting else "🔕 Отключить уведомления"
    btn_data = "notify_enable" if not current_setting else "notify_disable"
    
    markup.add(types.InlineKeyboardButton(btn_text, callback_data=btn_data))
    
    status = "✅ ВКЛЮЧЕНЫ" if current_setting else "❌ ОТКЛЮЧЕНЫ"
    
    bot.reply_to(message, 
        f"🔔 <b>Настройка уведомлений</b>\n\n"
        f"Статус: {status}\n\n"
        f"Вы будете получать уведомления о:\n"
        f"• Начале битвы с боссом\n"
        f"• Важных событиях игры", 
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data in ["notify_enable", "notify_disable"])
def toggle_notifications(call):
    user_id = call.from_user.id
    username = call.from_user.username
    
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.answer_callback_query(call.id, "Доступ запрещён", show_alert=True)
        return
    
    if call.data == "notify_enable":
        notification_settings[user_id] = True
        bot.answer_callback_query(call.id, "Уведомления включены!")
        bot.send_message(user_id, "✅ Уведомления ВКЛЮЧЕНЫ")
    else:
        notification_settings[user_id] = False
        bot.answer_callback_query(call.id, "Уведомления отключены!")
        bot.send_message(user_id, "❌ Уведомления ОТКЛЮЧЕНЫ")
# --- ГРУППОВЫЕ КОМАНДЫ ---

@bot.message_handler(commands=['create_game'])
def create_game(message):
    if message.chat.type == 'private':
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id in active_games:
        bot.reply_to(message, "В этом чате уже идет игра!")
        return
    
    allow_2v2 = is_monday()
    
    can_play, remaining = check_limits(user_id)
    if not can_play:
        bot.reply_to(message, "Лимит боев исчерпан!")
        return
    
    active_games[chat_id] = {
        'host': user_id,
        'host_nickname': get_user(user_id)[2] or message.from_user.first_name,
        'p1': None,
        'nickname_p1': None,
        'p2': None,
        'nickname_p2': None,
        'score_p1': 0,
        'score_p2': 0,
        'round': 1,
        'cards': {},
        'cards_submitted_p1': False,
        'cards_submitted_p2': False,
        'location': None,
        'location_name': None,
        'mode': '1v1',
        'consent': {},
        'draw_consent': {}
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 Я буду Игроком 1", callback_data="become_p1"))
    markup.add(types.InlineKeyboardButton("Я второй игрок", callback_data="join_p2"))
    
    if allow_2v2:
        markup.add(types.InlineKeyboardButton("Режим 2x2", callback_data="mode_2v2"))
    
    # Кнопка локации скрыта пока не выбраны оба игрока
    
    bot.send_message(chat_id, 
        f"🎮 <b>Игра создана!</b>\n"
        f"Ведущий: {escape_html(active_games[chat_id]['host_nickname'])}\n\n"
        f"<b>Настройки:</b>\n"
        f"• Нужны 2 РАЗНЫХ игрока для начала\n"
        f"• Можно выбрать локацию или играть без неё\n"
        f"• Формат: <code>1,2,3: 2,0,1</code> (номера карт: способности)\n"
        f"• Бот автоматически отправит картинки карт из колоды\n\n"
        f"Нажмите кнопку чтобы стать игроком:", 
        reply_markup=markup, parse_mode="HTML")

    """Обновляет кнопку локации - показывает только если оба игрока выбраны"""
    
    if game['p1'] is not None and game['p2'] is not None:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("▶️ Настроить локацию", callback_data="location_setup"))
        bot.send_message(chat_id, 
            "✅ **Оба игрока выбраны!**\n\nВедущий может настроить локацию:", 
            reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=['setup_group_commands'])
def setup_group_commands(message):
    """Настройка команд для конкретной группы"""
    
    if message.chat.type in ['group', 'supergroup']:
        group_commands = [
            types.BotCommand('r', '🎲 Бросить кубики'),
            types.BotCommand('s', '🎮 Создать игру'),
            types.BotCommand('locations', '📍 Список локаций')
        ]
        
        bot.set_my_commands(group_commands, types.BotCommandScopeChat(message.chat.id))
        
        bot.reply_to(message, 
            "✅ **Команды для этой группы настроены!**\n\n"
            "📋 Теперь в этой группе видны:\n"
            "/r - 🎲 Бросить кубики\n"
            "/s - 🎮 Создать игру\n"
            "/locations - 📍 Список локаций\n\n"
            "⚠️ В ЛС эти команды не видны!", 
            parse_mode="Markdown")
    else:
        bot.reply_to(message, 
            "⚠️ Эта команда работает **только в группах**!", 
            parse_mode="Markdown")

# --- КОРОТКИЕ КОМАНДЫ ДЛЯ ГРУППЫ ---

@bot.message_handler(commands=['r'])
def roll_short(message):
    if message.chat.type == 'private':
        bot.reply_to(message, 
            "⚠️ Команда `/r` работает **только в группах**!\n\n"
            "В ЛС используйте: /start, /name, /add, /my_cards, /delete, /surrender", 
            parse_mode="Markdown")
        return
    
    try:
        args = message.text.split()
        count = int(args[1]) if len(args) > 1 else 1
        
        if count <= 0 or count > 20:
            bot.reply_to(message, "Можно кидать от 1 до 20 кубиков")
            return
        
        results = [random.randint(1, 4) for _ in range(count)]
        success = 4 in results
        
        text = f"🎲 Результат {count}d4: {results}\n"
        text += "✅ УСПЕХ!" if success else "❌ Провал"
        
        bot.reply_to(message, text)
    except (IndexError, ValueError):
        bot.reply_to(message, "Использование: /r <число>")

@bot.message_handler(commands=['s'])
def start_game_short(message):
    if message.chat.type == 'private':
        bot.reply_to(message, 
            "⚠️ Команда `/s` работает **только в группах**!\n\n"
            "В ЛС используйте: /start, /name, /add, /my_cards, /delete, /surrender", 
            parse_mode="Markdown")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id in active_games:
        bot.reply_to(message, "⚠️ В этом чате уже идет игра!")
        return
    
    can_play, remaining = check_limits(user_id)
    if not can_play:
        bot.reply_to(message, "Лимит боев исчерпан!")
        return
    
    active_games[chat_id] = {
        'host': user_id,
        'host_nickname': get_user(user_id)[2] or message.from_user.first_name,
        'p1': None,
        'nickname_p1': None,
        'p2': None,
        'nickname_p2': None,
        'score_p1': 0,
        'score_p2': 0,
        'round': 1,
        'cards': {},
        'cards_submitted_p1': False,
        'cards_submitted_p2': False,
        'location': None,
        'location_name': None,
        'mode': '1v1',
        'consent': {},
        'draw_consent': {}
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 Я буду Игроком 1", callback_data="become_p1"))
    markup.add(types.InlineKeyboardButton("Я второй игрок", callback_data="join_p2"))
    
    if is_monday():
        markup.add(types.InlineKeyboardButton("Режим 2x2", callback_data="mode_2v2"))
    
    
    bot.send_message(chat_id, 
        f"🎮 <b>Игра создана!</b>\n"
        f"Ведущий: {escape_html(active_games[chat_id]['host_nickname'])}\n\n"
        f"Нажмите кнопку чтобы стать игроком:", 
        reply_markup=markup, parse_mode="HTML")

# --- ЛОГИКА ИГРЫ ---

@bot.callback_query_handler(func=lambda call: call.data == "become_p1")
def become_p1(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    # Проверка: игрок не может быть обоими игроками одновременно
    if call.from_user.id == game['p2']:
        bot.answer_callback_query(call.id, "❌ Вы уже Игрок 2! Нельзя быть обоими игроками!", show_alert=True)
        return
    
    if game['p1'] is None:
        game['p1'] = call.from_user.id
        game['nickname_p1'] = get_user(call.from_user.id)[2] or call.from_user.first_name
        game['consent'][game['p1']] = True
        bot.answer_callback_query(call.id, "Вы стали Игроком 1!")
        bot.send_message(chat_id, f"✅ {escape_html(game['nickname_p1'])} стал Игроком 1!")
        
  # Кнопка локации будет показана когда оба игрока выбраны
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Я второй игрок", callback_data="join_p2"))
        if is_monday():
            markup.add(types.InlineKeyboardButton("Режим 2x2", callback_data="mode_2v2"))
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    else:
        bot.answer_callback_query(call.id, "Место Игрока 1 уже занято!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "join_p2")
def join_game(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    # Проверка: игрок не может быть обоими игроками одновременно
    if call.from_user.id == game['p1']:
        bot.answer_callback_query(call.id, "❌ Вы уже Игрок 1! Нельзя быть обоими игроками!", show_alert=True)
        return

    if game['p2'] is None:
        game['p2'] = call.from_user.id
        game['nickname_p2'] = get_user(call.from_user.id)[2] or call.from_user.first_name
        game['consent'][call.from_user.id] = True
        
        bot.answer_callback_query(call.id, "Вы присоединились!")
        bot.send_message(chat_id, 
            f"Игрок 2: {escape_html(game['nickname_p2'])} присоединился!\n\n"
            f"Теперь можно выбрать локацию!", 
            parse_mode="HTML")
        
        # Обновляем кнопку локации - теперь доступна
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("▶️ Настроить локацию", callback_data="location_setup"))
        bot.send_message(chat_id, "✅ Оба игрока выбраны! Ведущий может настроить локацию:", reply_markup=markup)
    else:
        bot.answer_callback_query(call.id, "Место занято!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "mode_2v2")
def set_2v2_mode(call):
    chat_id = call.message.chat.id
    if chat_id in active_games:
        active_games[chat_id]['mode'] = '2v2'
        bot.answer_callback_query(call.id, "Режим 2x2 установлен")
        bot.send_message(chat_id, "🎮 Установлен режим 2x2")

@bot.callback_query_handler(func=lambda call: call.data == "location_setup")
def location_setup(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    # Проверка: оба игрока должны быть выбраны
    if game['p1'] is None or game['p2'] is None:
        bot.answer_callback_query(call.id, "Сначала нужны 2 игрока!", show_alert=True)
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎲 Случайная локация", callback_data="loc_random"))
    markup.add(types.InlineKeyboardButton("🚫 Без локации", callback_data="loc_none"))
    markup.add(types.InlineKeyboardButton("📍 Выбрать из списка", callback_data="loc_select"))
    
    bot.answer_callback_query(call.id)
    bot.send_message(chat_id, 
        f"📍 <b>Настройка локации</b>\n\n"
        f"Выберите вариант:", 
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "loc_random")
def loc_random(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if call.from_user.id != game['host']:
        return
    
    locations = get_locations()
    if locations:
        selected_loc = random.choice(locations)
        game['location'] = selected_loc[3]
        game['location_name'] = selected_loc[1]
        
        if selected_loc[3]:
            bot.send_photo(chat_id, selected_loc[3], 
                          caption=f"🎲 <b>Случайная локация: {escape_html(selected_loc[1])}</b>\n{escape_html(selected_loc[2])}", 
                          parse_mode="HTML")
        else:
            bot.send_message(chat_id, 
                            f"🎲 <b>Случайная локация: {escape_html(selected_loc[1])}</b>\n{escape_html(selected_loc[2])}", 
                            parse_mode="HTML")
        
        check_and_start_game(chat_id, game)
    else:
        bot.answer_callback_query(call.id, "Локации не загружены!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "loc_none")
def loc_none(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if call.from_user.id != game['host']:
        return
    
    game['location'] = None
    game['location_name'] = "Без локации"
    
    bot.answer_callback_query(call.id, "Без локации")
    bot.send_message(chat_id, 
        f"🚫 <b>Без локации</b>\nСтандартные правила", 
        parse_mode="HTML")
    
    check_and_start_game(chat_id, game)

@bot.callback_query_handler(func=lambda call: call.data == "loc_select")
def loc_select(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if call.from_user.id != game['host']:
        return
    
    locations = get_locations()
    if not locations:
        bot.answer_callback_query(call.id, "Локации не загружены!", show_alert=True)
        return
    
    markup = types.InlineKeyboardMarkup()
    for loc_id, name, desc, _ in locations[:8]:
        markup.add(types.InlineKeyboardButton(name, callback_data=f"loc_{loc_id}"))
    
    bot.answer_callback_query(call.id)
    bot.send_message(chat_id, 
        f"📍 <b>Выберите локацию:</b>", 
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("loc_"))
def loc_chosen(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if call.from_user.id != game['host']:
        return
    
    loc_id = int(call.data.split("_")[1])
    locations = get_locations()
    
    for lid, name, desc, fid in locations:
        if lid == loc_id:
            game['location'] = fid
            game['location_name'] = name
            
            if fid:
                bot.send_photo(chat_id, fid, 
                              caption=f"📍 <b>Локация: {escape_html(name)}</b>\n{escape_html(desc)}", 
                              parse_mode="HTML")
            else:
                bot.send_message(chat_id, 
                                f"📍 <b>Локация: {escape_html(name)}</b>\n{escape_html(desc)}", 
                                parse_mode="HTML")
            
            check_and_start_game(chat_id, game)
            break
    
    bot.answer_callback_query(call.id, f"Выбрана: {game['location_name']}")

def check_and_start_game(chat_id, game):
    if game['p1'] is None or game['p2'] is None:
        bot.send_message(chat_id, 
            f"✅ Локация выбрана: {escape_html(game['location_name'])}\n\n"
            f"⏳ Ждем игроков...", 
            parse_mode="HTML")
        return
    
    bot.send_message(chat_id, 
        f"🎮 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
        f"👥 {escape_html(game['nickname_p1'])} vs {escape_html(game['nickname_p2'])}\n"
        f"📍 Локация: {escape_html(game['location_name'])}\n\n"
        f"📩 Игроки, напишите в <b>ЛИЧНЫЕ СООБЩЕНИЯ</b> боту:\n"
        f"<code>1,2,3: 2,0,1</code>\n\n"
        f"⚠️ <b>Фото отправлять не нужно!</b>", 
        parse_mode="HTML")
    
    start_round(chat_id, game)

def start_round(chat_id, game):
    game['cards'] = {'p1': [], 'p2': []}
    game['cards_submitted_p1'] = False
    game['cards_submitted_p2'] = False
    game['draw_consent'] = {}  # Сброс голосования за ничью
    
    if game['p1'] in card_selections:
        del card_selections[game['p1']]
    if game['p2'] in card_selections:
        del card_selections[game['p2']]
    
    if is_friday():
        bot.send_message(chat_id, "🔄 <b>ПЯТНИЦА!</b> Сегодня вы используете карты соперников!", parse_mode="HTML")
    
    bot.send_message(chat_id, 
        f"⚔️ <b>Раунд {game['round']}</b>\n"
        f"📊 Счёт: {escape_html(game['nickname_p1'])} {game['score_p1']} : {escape_html(game['nickname_p2'])} {game['score_p2']}\n\n"
        f"📩 Напишите в <b>ЛС боту</b>: <code>1,2,3: 2,0,1</code>", 
        parse_mode="HTML")
# --- ОБРАБОТКА ОТПРАВКИ КАРТ ---

@bot.message_handler(content_types=['text'])
def handle_card_submission(message):
    user_id = message.from_user.id
    
    # ❌ ИГНОРИРУЕМ СООБЩЕНИЯ В ГРУППАХ - карты только в ЛС
    if message.chat.type != 'private':
        return
    
    # Ищем активную игру этого игрока
    found_chat = None
    found_game = None
    for chat_id, game in active_games.items():
        if user_id in [game.get('p1'), game.get('p2')]:
            found_chat = chat_id
            found_game = game
            break
    
    if not found_chat or not found_game:
        return
    
    game = found_game
    is_p1 = user_id == game['p1']
    is_p2 = user_id == game['p2']
    
    if not is_p1 and not is_p2:
        return
    
    # ✅ Проверяем отправил ли уже карты
    # Если ДРУГОЙ игрок ещё не отправил - можно изменить карты
    if is_p1 and game['cards_submitted_p1']:
        if game['cards_submitted_p2']:
            # Оба отправили - раунд начался, нельзя менять
            return
        # Другой ещё не отправил - можно изменить (тихо перезаписываем)
    if is_p2 and game['cards_submitted_p2']:
        if game['cards_submitted_p1']:
            # Оба отправили - раунд начался, нельзя менять
            return
        # Другой ещё не отправил - можно изменить (тихо перезаписываем)
    
    text = message.text.strip()
    
    if ':' not in text:
        bot.reply_to(message, 
            "❌ Неверный формат!\n\n"
            "<b>Правильный формат:</b> <code>1,2,3: 2,0,1</code>\n\n"
            "Пример: <code>1,2: 2 +5 атака, 0</code>", 
            parse_mode="HTML")
        return
    
    try:
        parts = text.split(':')
        card_nums_str = parts[0].strip()
        abilities_str = parts[1].strip() if len(parts) > 1 else ""
        
        card_nums = [int(x.strip()) for x in card_nums_str.split(',') if x.strip().isdigit()]
        
        if not card_nums:
            bot.reply_to(message, "❌ Укажите хотя бы одну карту!")
            return
        
        ability_details = []
        if abilities_str:
            ability_details = [x.strip() for x in abilities_str.split(',')]
        
        user_cards = get_user_cards(user_id)
        
        if is_friday():
            opponent_id = game['p2'] if is_p1 else game['p1']
            if opponent_id:
                user_cards = get_user_cards(opponent_id)
        
        cards_data = []
        for idx, card_num in enumerate(card_nums):
            card_found = None
            for cid, c_file_id, c_name in user_cards:
                if cid == card_num:
                    card_found = (cid, c_file_id, c_name)
                    break
            
            if not card_found:
                bot.reply_to(message, f"❌ Карта #{card_num} не найдена в вашей колоде!")
                return
            
            ability_text = ability_details[idx] if idx < len(ability_details) else "0"
            
            ability_num = 0
            details_text = ""
            
            for char in ability_text:
                if char.isdigit() and int(char) in [0, 1, 2, 3]:
                    ability_num = int(char)
                    details_idx = ability_text.index(char) + 1
                    details_text = ability_text[details_idx:].strip()
                    break
            
            cards_data.append({
                'file_id': card_found[1],
                'ability': ability_num,
                'details': details_text,
                'card_name': card_found[2],
                'card_id': card_found[0],
                'is_support': "поддержка" in card_found[2].lower()
            })
        
        # Сохраняем карты (можно перезаписать если соперник ещё не отправил)
        if is_p1:
            game['cards']['p1'] = cards_data
            game['cards_submitted_p1'] = True
            
            if game['cards_submitted_p2']:
                # Оба отправили - начинаем раунд
                bot.reply_to(message, 
                    f"✅ Карты приняты!\n"
                    f"🃏 Карт: {len(cards_data)}\n\n"
                    f"⚔️ Оба игрока готовы! Раунд начинается...", 
                    parse_mode="HTML")
                check_round_complete(found_chat, game)
            else:
                # Ждем соперника
                bot.reply_to(message, 
                    f"✅ Карты приняты!\n"
                    f"🃏 Карт: {len(cards_data)}\n\n"
                    f"⏳ Ждем соперника...\n"
                    f"💡 Можно изменить карты, пока соперник не отправил свои!", 
                    parse_mode="HTML")
        else:
            game['cards']['p2'] = cards_data
            game['cards_submitted_p2'] = True
            
            if game['cards_submitted_p1']:
                # Оба отправили - начинаем раунд
                bot.reply_to(message, 
                    f"✅ Карты приняты!\n"
                    f"🃏 Карт: {len(cards_data)}\n\n"
                    f"⚔️ Оба игрока готовы! Раунд начинается...", 
                    parse_mode="HTML")
                check_round_complete(found_chat, game)
            else:
                # Ждем соперника
                bot.reply_to(message, 
                    f"✅ Карты приняты!\n"
                    f"🃏 Карт: {len(cards_data)}\n\n"
                    f"⏳ Ждем соперника...\n"
                    f"💡 Можно изменить карты, пока соперник не отправил свои!", 
                    parse_mode="HTML")
        
    except (ValueError, IndexError) as e:
        bot.reply_to(message, 
            f"❌ Ошибка: {e}\n\n"
            "<b>Правильный формат:</b> <code>1,2,3: 2,0,1</code>", 
            parse_mode="HTML")

def check_round_complete(chat_id, game):
    if game['cards_submitted_p1'] and game['cards_submitted_p2']:
        reveal_cards(chat_id, game)

def reveal_cards(chat_id, game):
    p1_cards = game['cards']['p1']
    p2_cards = game['cards']['p2']
    
    media_group = []
    
    for card in p1_cards:
        caption = f"{escape_html(game['nickname_p1'])}\n"
        caption += f"🃏 {escape_html(card['card_name'])}\n"
        caption += f"⚡ Способность: {card['ability']}"
        if card['details']:
            caption += f"\n📝 {escape_html(card['details'])}"
        media_group.append(types.InputMediaPhoto(media=card['file_id'], caption=caption))
    
    for card in p2_cards:
        caption = f"{escape_html(game['nickname_p2'])}\n"
        caption += f"🃏 {escape_html(card['card_name'])}\n"
        caption += f"⚡ Способность: {card['ability']}"
        if card['details']:
            caption += f"\n📝 {escape_html(card['details'])}"
        media_group.append(types.InputMediaPhoto(media=card['file_id'], caption=caption))
    
    if media_group:
        for i in range(0, len(media_group), 10):
            chunk = media_group[i:i+10]
            bot.send_media_group(chat_id, chunk)
    
    p1_cards_summary = []
    for card in p1_cards:
        if card['details']:
            p1_cards_summary.append(f"{escape_html(card['card_name'])} (⚡{card['ability']} {escape_html(card['details'])})")
        else:
            p1_cards_summary.append(f"{escape_html(card['card_name'])} (⚡{card['ability']})")
    
    p2_cards_summary = []
    for card in p2_cards:
        if card['details']:
            p2_cards_summary.append(f"{escape_html(card['card_name'])} (⚡{card['ability']} {escape_html(card['details'])})")
        else:
            p2_cards_summary.append(f"{escape_html(card['card_name'])} (⚡{card['ability']})")
    
    p1_summary_text = ", ".join(p1_cards_summary) if p1_cards_summary else "Нет карт"
    p2_summary_text = ", ".join(p2_cards_summary) if p2_cards_summary else "Нет карт"
    
    bot.send_message(chat_id, 
        f"<b>Раунд {game['round']}</b>\n\n"
        f"👤 {escape_html(game['nickname_p1'])}:\n"
        f"   {p1_summary_text}\n\n"
        f"👤 {escape_html(game['nickname_p2'])}:\n"
        f"   {p2_summary_text}\n\n"
        f"Ведущий ({escape_html(game['host_nickname'])}), определите победителя:", 
        parse_mode="HTML")
    
    show_battle_buttons(chat_id, game)

def show_battle_buttons(chat_id, game):
    markup = types.InlineKeyboardMarkup()
    
    btn1 = types.InlineKeyboardButton(f"{game['nickname_p1']}", callback_data="win_p1")
    btn2 = types.InlineKeyboardButton(f"{game['nickname_p2']}", callback_data="win_p2")
    btn3 = types.InlineKeyboardButton("Ничья", callback_data="draw")
    btn4 = types.InlineKeyboardButton("Равная скорость", callback_data="equal_speed")
    
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    
    bot.send_message(chat_id, "Ведущий, выберите победителя:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "equal_speed")
def equal_speed_handler(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    first_player = random.choice(['p1', 'p2'])
    first_nick = game['nickname_p1'] if first_player == 'p1' else game['nickname_p2']
    
    bot.answer_callback_query(call.id, f"Случайный выбор: {first_nick} ходит первым!")
    bot.send_message(chat_id, 
        f"🎲 <b>Равная скорость!</b>\n\n"
        f"Случайным образом выбрано: <b>{escape_html(first_nick)}</b> ходит первым!", 
        parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("win_"))
def handle_win(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    winner = call.data.split("_")[1]
    
    if winner == 'p1':
        game['score_p1'] += 1
        winner_nick = game['nickname_p1']
    else:
        game['score_p2'] += 1
        winner_nick = game['nickname_p2']
    
    bot.answer_callback_query(call.id, f"{winner_nick} выиграл раунд!")
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    
    if game['score_p1'] >= 3 or game['score_p2'] >= 3:
        finish_game(chat_id, game)
    else:
        game['round'] += 1
        bot.send_message(chat_id, 
            f"✅ {escape_html(winner_nick)} выиграл раунд!\n\n"
            f"📊 Счёт: {escape_html(game['nickname_p1'])} {game['score_p1']} : {escape_html(game['nickname_p2'])} {game['score_p2']}", 
            parse_mode="HTML")
        start_round(chat_id, game)

@bot.callback_query_handler(func=lambda call: call.data == "draw")
def handle_draw(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    game['draw_consent'] = {
        'p1': False,
        'p2': False
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Согласен на ничью", callback_data="agree_draw"))
    markup.add(types.InlineKeyboardButton("❌ Отказ", callback_data="reject_draw"))
    
    bot.send_message(chat_id, 
        f"⚖️ <b>Ведущий предложил ничью!</b>\n\n"
        f"⚠️ Для ничьи нужно согласие ОБЕИХ игроков!\n\n"
        f"Игроки, проголосуйте:", 
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data in ["agree_draw", "reject_draw"])
def handle_draw_vote(call):
    chat_id = call.message.chat.id
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    user_id = call.from_user.id
    
    if user_id not in [game['p1'], game['p2']]:
        bot.answer_callback_query(call.id, "Только игроки могут голосовать!", show_alert=True)
        return
    
    if 'draw_consent' not in game:
        bot.answer_callback_query(call.id, "Голосование не активно!", show_alert=True)
        return
    
    if call.data == "agree_draw":
        if user_id == game['p1']:
            if game['draw_consent']['p1']:
                bot.answer_callback_query(call.id, "Вы уже согласились!", show_alert=True)
                return
            game['draw_consent']['p1'] = True
            bot.answer_callback_query(call.id, "Вы согласились на ничью")
        elif user_id == game['p2']:
            if game['draw_consent']['p2']:
                bot.answer_callback_query(call.id, "Вы уже согласились!", show_alert=True)
                return
            game['draw_consent']['p2'] = True
            bot.answer_callback_query(call.id, "Вы согласились на ничью")
    else:
        bot.answer_callback_query(call.id, "Вы отказались от ничьи")
        bot.send_message(chat_id, f"❌ {escape_html(game['nickname_p1'] if user_id == game['p1'] else game['nickname_p2'])} отказался от ничьи. Игра продолжается.")
        game['draw_consent'] = {}
        show_battle_buttons(chat_id, game)
        return
    
    if game['draw_consent'].get('p1', False) and game['draw_consent'].get('p2', False):
        bot.send_message(chat_id, "✅ Оба игрока согласились на ничью!")
        finish_game_draw(chat_id, game)
    else:
        p1_status = "✅" if game['draw_consent'].get('p1', False) else "⏳"
        p2_status = "✅" if game['draw_consent'].get('p2', False) else "⏳"
        bot.send_message(chat_id, 
            f"🗳️ Голосование за ничью:\n\n"
            f"{p1_status} {escape_html(game['nickname_p1'])}\n"
            f"{p2_status} {escape_html(game['nickname_p2'])}\n\n"
            f"⚠️ Ждем согласия обоих игроков!", 
            parse_mode="HTML")

def finish_game(chat_id, game):
    winner_nick = game['nickname_p1'] if game['score_p1'] >= 3 else game['nickname_p2']
    loser_nick = game['nickname_p2'] if game['score_p1'] >= 3 else game['nickname_p1']
    loser_score = game['score_p2'] if game['score_p1'] >= 3 else game['score_p1']
    
    winner_id = game['p1'] if game['score_p1'] >= 3 else game['p2']
    loser_id = game['p2'] if game['score_p1'] >= 3 else game['p1']
    
    if loser_score == 0:
        w_coins, l_coins = 3, 0
    else:
        w_coins, l_coins = 2, 1
    
    w_total, w_rem = update_user_stats(winner_id, w_coins, True)
    l_total, l_rem = update_user_stats(loser_id, l_coins, True)
    
    today = datetime.date.today()
    limit = 14 if today.weekday() == 5 else 7
    
    text = (f"🏆 <b>ИГРА ОКОНЧЕНА!</b>\n\n"
            f"🥇 Победитель: <b>{escape_html(winner_nick)}</b>\n"
            f"📊 Финальный счёт: {game['score_p1']} : {game['score_p2']}\n\n"
            f"💰 <b>Награды:</b>\n"
            f"🥇 {escape_html(winner_nick)}:\n"
            f"   • Всего монет: {w_total}\n"
            f"   • +{w_coins} за бой\n"
            f"   • Осталось боев: {w_rem}/{limit}\n"
            f"🥈 {escape_html(loser_nick)}:\n"
            f"   • Всего монет: {l_total}\n"
            f"   • +{l_coins} за бой\n"
            f"   • Осталось боев: {l_rem}/{limit}")
    
    bot.send_message(chat_id, text, parse_mode="HTML")
    del active_games[chat_id]

def finish_game_draw(chat_id, game):
    p1_total, p1_rem = update_user_stats(game['p1'], 1, True)
    p2_total, p2_rem = update_user_stats(game['p2'], 1, True)
    
    today = datetime.date.today()
    limit = 14 if today.weekday() == 5 else 7
    
    text = (f"⚖️ <b>НИЧЬЯ!</b>\n\n"
            f"📊 Финальный счёт: {game['score_p1']} : {game['score_p2']}\n\n"
            f"💰 <b>Награды:</b>\n"
            f"{escape_html(game['nickname_p1'])}:\n"
            f"   • Всего монет: {p1_total}\n"
            f"   • +1 за бой\n"
            f"   • Осталось боев: {p1_rem}/{limit}\n"
            f"{escape_html(game['nickname_p2'])}:\n"
            f"   • Всего монет: {p2_total}\n"
            f"   • +1 за бой\n"
            f"   • Осталось боев: {p2_rem}/{limit}")
    
    bot.send_message(chat_id, text, parse_mode="HTML")
    del active_games[chat_id]
# --- БОЙ С БОССОМ ---

@bot.message_handler(commands=['boss_battle'])
def create_boss_battle(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_sunday():
        bot.reply_to(message, "⚠️ Битва с боссом доступна только в воскресенье!")
        return
    
    if chat_id in boss_battles:
        bot.reply_to(message, "Битва с боссом уже создана!")
        return
    
    boss_battles[chat_id] = {
        'organizer': None,
        'participants': {},
        'start_time': None,
        'round': 1,
        'cards': {},
        'status': 'waiting'
    }
    
    bot.reply_to(message, 
        "👹 <b>БИТВА С БОССОМ</b>\n\n"
        "В 12:00 будет создан опрос для участников\n"
        "Организатор получит уведомление в 8:00\n\n"
        "Ожидайте уведомлений!", 
        parse_mode="HTML")

@bot.message_handler(commands=['boss_time'])
def set_boss_time(message):
    global ORGANIZER_ID
    user_id = message.from_user.id
    
    if ORGANIZER_ID and user_id != ORGANIZER_ID:
        bot.reply_to(message, "Только организатор может установить время!")
        return
    
    try:
        hours = int(message.text.split()[1])
        minutes = int(message.text.split()[2])
        
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            bot.reply_to(message, "Неверное время!")
            return
        
        chat_id = message.chat.id
        if chat_id in boss_battles:
            boss_battles[chat_id]['start_time'] = datetime.time(hours, minutes)
            boss_battles[chat_id]['organizer'] = user_id
            
            notify_time = datetime.datetime.combine(datetime.date.today(), 
                                                   datetime.time(hours, minutes))
            
            scheduler.add_job(
                lambda: bot.send_message(chat_id, "⏰ <b>До битвы с боссом остался 1 час!</b>", parse_mode="HTML"),
                DateTrigger(run_date=notify_time - datetime.timedelta(hours=1)),
                id=f'boss_1h_{chat_id}'
            )
            
            scheduler.add_job(
                lambda: bot.send_message(chat_id, "⏰ <b>До битвы с боссом осталось 5 минут!</b>", parse_mode="HTML"),
                DateTrigger(run_date=notify_time - datetime.timedelta(minutes=5)),
                id=f'boss_5m_{chat_id}'
            )
            
            bot.reply_to(message, f"✅ Время битвы установлено: {hours:02d}:{minutes:02d}")
    except (IndexError, ValueError):
        bot.reply_to(message, "Использование: /boss_time <часы> <минуты>")

@bot.message_handler(commands=['boss_reward'])
def boss_reward(message):
    global ORGANIZER_ID
    user_id = message.from_user.id
    
    if ORGANIZER_ID and user_id != ORGANIZER_ID:
        bot.reply_to(message, "Только организатор!")
        return
    
    try:
        target_id = int(message.text.split()[1])
        coins = int(message.text.split()[2])
        
        total, rem = update_user_stats(target_id, coins, True)
        target = get_user(target_id)
        
        today = datetime.date.today()
        limit = 14 if today.weekday() == 5 else 7
        
        bot.reply_to(message, 
            f"✅ {escape_html(target[2] or str(target_id))} получил {coins} монет!\n"
            f"💰 Всего: {total}\n"
            f"⚔️ Осталось боев: {rem}/{limit}")
    except (IndexError, ValueError):
        bot.reply_to(message, "Использование: /boss_reward <user_id> <монеты>")

# --- СКРЫТЫЕ АДМИН-КОМАНДЫ ---

@bot.message_handler(commands=['dev_commands'])
def dev_commands(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        return
    
    text = (f"🛠️ <b>DEV COMMANDS</b>\n\n"
            f"/test_mode — Вкл/Выкл режим теста\n"
            f"/upload_location | Name | Desc — Загрузить локацию\n"
            f"/schedule_message YYYY-MM-DD HH:MM notify|no_notify text\n"
            f"/boss_reward <user_id> <coins> — Награда от босса\n"
            f"/boss_time <h> <m> — Время боя с боссом\n"
            f"/stats_user <id> — Статистика игрока\n"
            f"/notifications — Настройка уведомлений")
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['test_mode'])
def test_mode(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "Доступ запрещён")
        return
    
    user = get_user(message.from_user.id)
    if user[6] == 0:
        update_user(message.from_user.id, is_test_mode=1)
        bot.reply_to(message, "✅ Режим тестирования ВКЛЮЧЕН")
    else:
        update_user(message.from_user.id, is_test_mode=0)
        bot.reply_to(message, "✅ Режим тестирования ВЫКЛЮЧЕН")

@bot.message_handler(commands=['upload_location'])
def upload_location(message):
    global ORGANIZER_ID
    user_id = message.from_user.id
    
    if ORGANIZER_ID and user_id != ORGANIZER_ID:
        bot.reply_to(message, "Только организатор!")
        return
    
    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "Ответьте на фото локации этой командой")
        return
    
    try:
        parts = message.text.split(' | ')
        name = parts[1].strip()
        desc = parts[2].strip()
    except (IndexError, ValueError):
        bot.reply_to(message, "Использование: /upload_location | Название | Описание")
        return
    
    file_id = message.reply_to_message.photo[-1].file_id
    
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO locations (name, description, file_id) VALUES (?, ?, ?)",
              (name, desc, file_id))
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"✅ Локация '{name}' загружена!")

@bot.message_handler(commands=['schedule_message'])
def schedule_message_cmd(message):
    global ORGANIZER_ID
    user_id = message.from_user.id
    
    if ORGANIZER_ID and user_id != ORGANIZER_ID:
        bot.reply_to(message, "Только организатор!")
        return
    
    try:
        parts = message.text.split(maxsplit=4)
        date_str = parts[1]
        time_str = parts[2]
        notify_type = parts[3]
        text = parts[4]
        
        schedule_time = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        
        conn = sqlite3.connect('game_bot.db')
        c = conn.cursor()
        c.execute("""INSERT INTO scheduled_messages 
                    (chat_id, message_text, notify_text, schedule_time, notify_before, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                 (message.chat.id, text, 
                  text if notify_type == "notify" else None,
                  schedule_time.isoformat(),
                  3600 if notify_type == "notify" else 0,
                  user_id))
        conn.commit()
        conn.close()
        
        if notify_type == "notify":
            scheduler.add_job(
                lambda: bot.send_message(message.chat.id, 
                                        f"⏰ Через 1 час: {text}", parse_mode="HTML"),
                DateTrigger(run_date=schedule_time - datetime.timedelta(hours=1)),
                id=f'sched_notify_1h_{message.chat.id}_{schedule_time.timestamp()}'
            )
            
            scheduler.add_job(
                lambda: bot.send_message(message.chat.id, 
                                        f"⏰ Через 5 минут: {text}", parse_mode="HTML"),
                DateTrigger(run_date=schedule_time - datetime.timedelta(minutes=5)),
                id=f'sched_notify_5m_{message.chat.id}_{schedule_time.timestamp()}'
            )
        
        scheduler.add_job(
            lambda: bot.send_message(message.chat.id, text),
            DateTrigger(run_date=schedule_time),
            id=f'sched_msg_{message.chat.id}_{schedule_time.timestamp()}'
        )
        
        bot.reply_to(message, f"✅ Сообщение запланировано на {schedule_time}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
# --- ЕЖЕДНЕВНЫЕ СОБЫТИЯ ---

def setup_daily_events():
    events = {
        'mon': "📅 <b>ПОНЕДЕЛЬНИК!</b>\n\nКомандные бои! Возможность проводить бои 2 на 2!!!",
        'tue': "📅 <b>ВТОРНИК!</b>\n\nТурнир в колизее! Победитель получит новую карту!",
        'wed': "📅 <b>СРЕДА!</b>\n\nОткрытие магазина!",
        'thu': "📅 <b>ЧЕТВЕРГ!</b>\n\nРозыгрыш карты! Случайный игрок получает Серую карту!",
        'fri': "📅 <b>ПЯТНИЦА!</b>\n\nСмена сил! Используйте карты соперников!",
        'sat': "📅 <b>СУББОТА!</b>\n\nБезграничные бои! Лимит увеличен до 14!",
        'sun': "📅 <b>ВОСКРЕСЕНЬЕ!</b>\n\nБОСС НЕДЕЛИ! Все против босса!"
    }
    
    for day, text in events.items():
        scheduler.add_job(
            lambda t=text: None,
            CronTrigger(day_of_week=day, hour=0, minute=0),
            id=f'{day}_event'
        )

# --- ЗАПУСК ---

if __name__ == '__main__':
    init_db()
    setup_daily_events()
    setup_bot_commands()
    
    print("=" * 50)
    print("БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"Организатор: @{ORGANIZER_USERNAME}")
    print(f"Тестировщик: @{TEST_MODE_USER}")
    print("=" * 50)
    print("ВАЖНО: Попросите @Kitenokowo13 написать /start")
    print("для регистрации как организатор!")
    print("=" * 50)
    print("Бот готов к работе...")
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\nБот остановлен")
        scheduler.shutdown()
