import telebot
from telebot import types
import sqlite3
import random
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8766706568:AAHlUlZqYWQq9DvIJYoF0wIb3fu3gHJld74'
ORGANIZER_USERNAME = 'Kitenokowo13'
ORGANIZER_ID = None
TEST_MODE_USER = 'angel_zam'
bot = telebot.TeleBot(BOT_TOKEN)

scheduler = BackgroundScheduler()
scheduler.start()

active_games = {}
boss_battles = {}
user_ids = {}
game_messages = {}
player_challenges = {}
notification_settings = {}

def escape_html(text):
    if text is None:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

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
        is_test_mode INTEGER DEFAULT 0,
        short_id INTEGER UNIQUE
    )''')
    
    try:
        c.execute("ALTER TABLE users ADD COLUMN short_id INTEGER UNIQUE")
    except:
        pass
    
    c.execute('''CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        file_id TEXT,
        card_name TEXT,
        uploaded_date TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        file_id TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS battle_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id INTEGER,
        player2_id INTEGER,
        player1_wins INTEGER DEFAULT 0,
        player2_wins INTEGER DEFAULT 0,
        draws INTEGER DEFAULT 0,
        UNIQUE(player1_id, player2_id)
    )''')
    
    # Генерация коротких ID
    c.execute("SELECT user_id FROM users WHERE short_id IS NULL")
    users = c.fetchall()
    c.execute("SELECT short_id FROM users WHERE short_id IS NOT NULL")
    used_ids = set(row[0] for row in c.fetchall() if row[0])
    
    for (user_id,) in users:
        for i in range(1, 100):
            if i not in used_ids:
                c.execute("UPDATE users SET short_id = ? WHERE user_id = ?", (i, user_id))
                used_ids.add(i)
                break
    
    # Локации
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        locations = [
            ('ГОРЫ СЕВЕРА', 'Если скорость карт равна, каждая может промахнуться (1d4)', None),
            ('ЮЖНЫЕ ПОЛЯ', 'Атака противника -1, если вы используете поддержку', None),
            ('Город', 'Вас нельзя убить с 1 удара', None),
            ('Арена', 'При снижении защиты теряется скорость', None),
            ('ЧИСТИЛИЩЕ', 'Разница скорости = доп. броски кубика', None),
            ('ЭЛЬФИЙСКИЙ ЛЕС', 'Карты с тактикой 0 не могут использовать способности', None),
            ('Таверна', 'Поддержка имеет двойной эффект', None),
            ('ВЕЛИКАЯ ПУСТОШЬ', 'В начале раунда карты получают 1 урон', None)
        ]
        c.executemany("INSERT INTO locations (name, description, file_id) VALUES (?, ?, ?)", locations)
    
    conn.commit()
    conn.close()

def get_short_id(user_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT short_id FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        return result[0]
    
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT short_id FROM users WHERE short_id IS NOT NULL")
    used = set(row[0] for row in c.fetchall() if row[0])
    for i in range(1, 100):
        if i not in used:
            c.execute("UPDATE users SET short_id = ? WHERE user_id = ?", (i, user_id))
            conn.commit()
            conn.close()
            return i
    conn.close()
    return 99

def get_user_by_short_id(short_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE short_id = ?", (short_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def setup_bot_commands():
    try:
        group_commands = [
            types.BotCommand('duel', '⚔️ Вызвать игрока'),
            types.BotCommand('list', '📋 Список игроков'),
            types.BotCommand('r', '🎲 Кубики'),
            types.BotCommand('s', '🎮 Начать игру'),
            types.BotCommand('locations', '📍 Локации')
        ]
        
        private_commands = [
            types.BotCommand('start', '🚀 Старт'),
            types.BotCommand('name', '👤 Прозвище'),
            types.BotCommand('add', '🃏 Загрузить карту'),
            types.BotCommand('my_cards', '📚 Мои карты'),
            types.BotCommand('delete', '🗑️ Удалить'),
            types.BotCommand('surrender', '🏳️ Сдаться'),
            types.BotCommand('stats', '📊 Статистика'),
            types.BotCommand('get_id', '🆔 Мой ID')
        ]
        
        bot.set_my_commands(group_commands)
        bot.set_my_commands(private_commands, types.BotCommandScopeDefault())
        print("✅ Команды настроены")
    except Exception as e:
        print(f"⚠️ Ошибка команд: {e}")

def get_user(user_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user = (user_id, None, None, 0, 0, None, 0, None)
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
    return (True, limit - user[4]) if user[4] < limit else (False, 0)

def update_user_stats(user_id, coins_change, battle_played, opponent_id=None, won=False, draw=False):
    user = get_user(user_id)
    today = datetime.date.today().isoformat()
    coins = user[3] + coins_change
    battles = 0 if user[5] != today else user[4]
    if battle_played:
        battles += 1
    update_user(user_id, coins=coins, battles_today=battles, last_play_date=today)
    return coins, battles

def update_battle_stats(player1_id, player2_id, player1_won, draw):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM battle_stats WHERE (player1_id = ? AND player2_id = ?) OR (player1_id = ? AND player2_id = ?)",
              (player1_id, player2_id, player2_id, player1_id))
    record = c.fetchone()
    today = datetime.date.today().isoformat()
    
    if record:
        if draw:
            c.execute("UPDATE battle_stats SET draws = draws + 1 WHERE id = ?", (record[0],))
        elif player1_won:
            c.execute("UPDATE battle_stats SET player1_wins = player1_wins + 1 WHERE id = ?", (record[0],))
        else:
            c.execute("UPDATE battle_stats SET player2_wins = player2_wins + 1 WHERE id = ?", (record[0],))
    else:
        if draw:
            c.execute("INSERT INTO battle_stats (player1_id, player2_id, draws) VALUES (?, ?, 1)", (player1_id, player2_id))
        elif player1_won:
            c.execute("INSERT INTO battle_stats (player1_id, player2_id, player1_wins) VALUES (?, ?, 1)", (player1_id, player2_id))
        else:
            c.execute("INSERT INTO battle_stats (player1_id, player2_id, player2_wins) VALUES (?, ?, 1)", (player1_id, player2_id))
    
    conn.commit()
    conn.close()

def get_battle_stats(player_id):
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("""
        SELECT 
            CASE WHEN player1_id = ? THEN player2_id ELSE player1_id END,
            CASE WHEN player1_id = ? THEN player1_wins ELSE player2_wins END,
            CASE WHEN player1_id = ? THEN player2_wins ELSE player1_wins END,
            draws
        FROM battle_stats WHERE player1_id = ? OR player2_id = ?
    """, (player_id, player_id, player_id, player_id, player_id))
    stats = c.fetchall()
    conn.close()
    return stats

def get_all_players():
    conn = sqlite3.connect('game_bot.db')
    c = conn.cursor()
    c.execute("""
        SELECT u.user_id, u.short_id, u.nickname, u.username, u.coins,
            COALESCE(SUM(bs.player1_wins), 0) + COALESCE(SUM(bs.player2_wins), 0),
            COALESCE(SUM(CASE WHEN bs.player1_id = u.user_id THEN bs.player2_wins ELSE bs.player1_wins END), 0),
            COALESCE(SUM(bs.draws), 0)
        FROM users u
        LEFT JOIN battle_stats bs ON u.user_id = bs.player1_id OR u.user_id = bs.player2_id
        WHERE u.short_id IS NOT NULL
        GROUP BY u.user_id ORDER BY u.short_id
    """)
    players = c.fetchall()
    conn.close()
    return players

def is_monday(): return datetime.datetime.today().weekday() == 0
def is_friday(): return datetime.datetime.today().weekday() == 4
def is_sunday(): return datetime.datetime.today().weekday() == 6
# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    global ORGANIZER_ID
    user_id = message.from_user.id
    username = message.from_user.username
    short_id = get_short_id(user_id)
    
    if username:
        user_ids[username] = user_id
    
    if username == ORGANIZER_USERNAME:
        ORGANIZER_ID = user_id
        update_user(user_id, username=username)
        bot.send_message(user_id, "✅ Вы зарегистрированы как ОРГАНИЗАТОР!")
    
    user = get_user(user_id)
    update_user(user_id, username=username)
    
    first_name = escape_html(message.from_user.first_name)
    nickname = escape_html(user[2] if user[2] else 'Не установлено')
    
    text = (f"🎮 <b>Привет, {first_name}!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{short_id}</code>\n"
            f"💰 Монеты: {user[3]}\n"
            f"⚔️ Боёв: {user[4]}/7 (14 в сб)\n"
            f"👤 Прозвище: {nickname}\n\n"
            f"<b>Команды:</b>\n"
            f"/stats, /name, /add, /my_cards, /delete, /surrender, /get_id")
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['get_id'])
def get_id(message):
    short_id = get_short_id(message.from_user.id)
    user_id = message.from_user.id
    username = escape_html(message.from_user.username or "Нет")
    nickname = escape_html(get_user(user_id)[2] or "Не установлено")
    
    text = (f"👤 <b>Ваша информация:</b>\n\n"
            f"🆔 <b>Короткий ID:</b> <code>{short_id}</code>\n"
            f"🔢 Telegram ID: <code>{user_id}</code>\n"
            f"📛 Username: @{username}\n"
            f"🎭 Прозвище: {nickname}\n\n"
            f"💡 Для вызова: <code>/duel {short_id}</code>")
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    today = datetime.date.today()
    limit = 14 if today.weekday() == 5 else 7
    battles = user[4] if user[5] == today.isoformat() else 0
    short_id = get_short_id(user_id)
    nickname = escape_html(user[2] if user[2] else 'Не установлено')
    battle_stats = get_battle_stats(user_id)
    
    text = (f"📊 <b>Статистика</b>\n"
            f"🆔 ID: <code>{short_id}</code>\n"
            f"💰 Монеты: {user[3]}\n"
            f"⚔️ Боёв: {battles}/{limit}\n"
            f"📅 Осталось: {limit - battles}\n"
            f"👤 Прозвище: {nickname}\n\n")
    
    if battle_stats:
        text += f"<b>📈 Бои:</b>\n"
        for opponent_id, my_wins, opponent_wins, draws in battle_stats:
            opp_short = get_short_id(opponent_id)
            opp_nick = escape_html(get_user(opponent_id)[2] or f"Игрок {opp_short}")
            text += f"🆚 {opp_nick} (ID:{opp_short}): {my_wins}П / {opponent_wins}П / {draws}Н\n"
    else:
        text += "📈 Бои: Пока нет"
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['stats_user'])
def stats_user(message):
    """Статистика другого игрока (для организатора и тестировщика)"""
    username = message.from_user.username
    user_id = message.from_user.id
    
    # Проверяем права (организатор ИЛИ тестировщик)
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Только организатор и тестировщик!")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "❌ Укажите ID игрока!\n\nИспользование: /stats_user <ID>")
            return
        
        target_id = int(args[1])
        target = get_user(target_id)
        
        today = datetime.date.today()
        limit = 14 if today.weekday() == 5 else 7
        battles = target[4] if target[5] == today.isoformat() else 0
        
        nickname = escape_html(target[2] if target[2] else 'Не установлено')
        username_target = escape_html(target[1] if target[1] else 'Нет')
        short_id = get_short_id(target_id)
        
        text = (f"📊 <b>Статистика игрока</b>\n\n"
                f"🆔 Короткий ID: <code>{short_id}</code>\n"
                f"🔢 Telegram ID: <code>{target_id}</code>\n"
                f"📛 Username: @{username_target}\n"
                f"🏷️ Прозвище: {nickname}\n"
                f"💰 Монеты: {target[3]}\n"
                f"⚔️ Боёв сегодня: {battles}/{limit}\n"
                f"📅 Осталось боев: {limit - battles}")
        
        bot.reply_to(message, text, parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "❌ ID должен быть числом!\n\nИспользование: /stats_user <ID>")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['name'])
def set_nickname(message):
    try:
        nickname = message.text.split(' ', 1)[1].strip()
        if len(nickname) > 20:
            bot.reply_to(message, "Слишком длинное!")
            return
        update_user(message.from_user.id, nickname=nickname)
        bot.reply_to(message, f"✅ Прозвище: {nickname}")
    except IndexError:
        bot.reply_to(message, "/name прозвище")

@bot.message_handler(commands=['add'])
def upload_card(message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "⚠️ Ответьте на фото карты!")
        return
    try:
        card_name = message.text.split(' ', 1)[1].strip()
    except IndexError:
        bot.reply_to(message, "⚠️ Укажите название: /add название")
        return
    file_id = message.reply_to_message.photo[-1].file_id
    add_card(message.from_user.id, file_id, card_name)
    bot.reply_to(message, f"✅ Карта '<b>{escape_html(card_name)}</b>' загружена!", parse_mode="HTML")

@bot.message_handler(commands=['my_cards'])
def my_cards(message):
    cards = get_user_cards(message.from_user.id)
    if not cards:
        bot.reply_to(message, "Нет карт")
        return
    for idx, (cid, fid, name) in enumerate(cards, 1):
        is_support = name.lower().endswith('поддержка')
        cap = f"🃏 <b>Карта #{idx}</b>\nID: <code>{cid}</code>\nНазвание: {escape_html(name)}"
        if is_support:
            cap += "\n✨ <b>Поддержка</b> (не считается в лимите)"
        bot.send_photo(message.from_user.id, fid, cap, parse_mode="HTML")
    bot.send_message(message.from_user.id, f"📇 Всего: {len(cards)}", parse_mode="HTML")

@bot.message_handler(commands=['delete'])
def delete_card_cmd(message):
    try:
        cid = int(message.text.split()[1])
        card = delete_card(cid, message.from_user.id)
        if card:
            bot.reply_to(message, "✅ Удалено")
        else:
            bot.reply_to(message, "Не найдено")
    except:
        bot.reply_to(message, "/delete ID")

@bot.message_handler(commands=['surrender'])
def surrender(message):
    user_id = message.from_user.id
    for chat_id, game in list(active_games.items()):
        if user_id in [game.get('p1'), game.get('p2')]:
            winner_id = game['p2'] if user_id == game['p1'] else game['p1']
            wnick = game['nickname_p2'] if user_id == game['p1'] else game['nickname_p1']
            update_user_stats(winner_id, 3, True)
            update_user_stats(user_id, 0, True)
            bot.send_message(chat_id, f"🏆 {escape_html(wnick)} победил!")
            del active_games[chat_id]
            return
    bot.reply_to(message, "Вы не в игре")

@bot.message_handler(commands=['locations'])
def show_locations(message):
    locs = get_locations()
    if not locs:
        bot.reply_to(message, "Нет локаций")
        return
    text = "📍 <b>Локации:</b>\n\n"
    for _, name, desc, _ in locs:
        text += f"<b>{escape_html(name)}</b>\n{escape_html(desc)}\n\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['duel'])
def duel_player(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "⚠️ Только в группах!")
        return
    try:
        target_short = int(message.text.split()[1])
        if target_short < 1 or target_short > 99:
            bot.reply_to(message, "❌ ID от 1 до 99!")
            return
        
        target_id = get_user_by_short_id(target_short)
        if not target_id:
            bot.reply_to(message, f"❌ Игрок ID:{target_short} не найден!")
            return
        if target_id == message.from_user.id:
            bot.reply_to(message, "❌ Нельзя вызвать себя!")
            return
        
        can_play, _ = check_limits(message.from_user.id)
        if not can_play:
            bot.reply_to(message, "Лимит боев!")
            return
        
        chal_short = get_short_id(message.from_user.id)
        chal_nick = get_user(message.from_user.id)[2] or f"Игрок {chal_short}"
        targ_nick = get_user(target_id)[2] or f"Игрок {target_short}"
        
        player_challenges[message.chat.id] = {
            'challenger': message.from_user.id,
            'challenger_nick': chal_nick,
            'target': target_id,
            'target_nick': targ_nick
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Принять", callback_data="accept_duel"))
        markup.add(types.InlineKeyboardButton("❌ Отклонить", callback_data="decline_duel"))
        
        bot.send_message(message.chat.id, 
            f"⚔️ <b>ВЫЗОВ!</b>\n\n"
            f"{escape_html(chal_nick)} (ID:{chal_short}) вызывает\n"
            f"{escape_html(targ_nick)} (ID:{target_short})\n\n"
            f"Примите вызов!", 
            reply_markup=markup, parse_mode="HTML")
        
        # Истекает через 1 минуту
        scheduler.add_job(
            lambda: cleanup_challenge(message.chat.id),
            DateTrigger(run_date=datetime.datetime.now() + datetime.timedelta(minutes=1)),
            id=f'duel_{message.chat.id}'
        )
    except:
        bot.reply_to(message, "/duel ID")

def cleanup_challenge(chat_id):
    if chat_id in player_challenges:
        bot.send_message(chat_id, "⏰ Вызов истёк!")
        del player_challenges[chat_id]

@bot.message_handler(commands=['list'])
def list_players(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "⚠️ Только в группах!")
        return
    players = get_all_players()
    if not players:
        bot.reply_to(message, "Нет игроков")
        return
    text = "📋 <b>Игроки:</b>\n\n"
    for uid, short_id, nick, username, coins, wins, losses, draws in players:
        text += f"🆔 <b>ID:{short_id}</b> — {escape_html(nick or f'Игрок {short_id}')} 💰{coins}\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['all_commands'])
def all_commands(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    
    text = (f"🛠️ <b>ВСЕ КОМАНДЫ</b>\n\n"
            f"<b>📱 Основные:</b>\n"
            f"/start, /name, /add, /my_cards, /delete, /surrender, /stats, /duel, /list, /r, /s, /locations, /get_id\n\n"
            f"<b>🔧 Организатор:</b>\n"
            f"/stats_user, /boss_reward, /boss_time, /upload_location, /schedule_message, /notifications\n\n"
            f"<b>🧪 Тестировщик:</b>\n"
            f"/test_mode, /add_coins, /reset_battles")
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['notifications'])
def notifications_settings(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "Доступ запрещён")
        return
    
    markup = types.InlineKeyboardMarkup()
    current = notification_settings.get(message.from_user.id, False)
    btn_text = "🔔 Включить" if not current else "🔕 Отключить"
    btn_data = "notify_enable" if not current else "notify_disable"
    markup.add(types.InlineKeyboardButton(btn_text, callback_data=btn_data))
    
    status = "✅ ВКЛ" if current else "❌ ВЫКЛ"
    bot.reply_to(message, f"🔔 Уведомления: {status}", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data in ["notify_enable", "notify_disable"])
def toggle_notifications(call):
    username = call.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.answer_callback_query(call.id, "Запрещено", show_alert=True)
        return
    
    if call.data == "notify_enable":
        notification_settings[call.from_user.id] = True
        bot.answer_callback_query(call.id, "Включено!")
    else:
        notification_settings[call.from_user.id] = False
        bot.answer_callback_query(call.id, "Отключено!")
# --- ГРУППОВЫЕ КОМАНДЫ ---

@bot.message_handler(commands=['create_game'])
def create_game(message):
    if message.chat.type == 'private':
        return
    if message.chat.id in active_games:
        bot.reply_to(message, "Игра уже идет!")
        return
    
    can_play, _ = check_limits(message.from_user.id)
    if not can_play:
        bot.reply_to(message, "Лимит боев!")
        return
    
    active_games[message.chat.id] = {
        'host': message.from_user.id,
        'host_nickname': get_user(message.from_user.id)[2] or message.from_user.first_name,
        'p1': None, 'nickname_p1': None,
        'p2': None, 'nickname_p2': None,
        'score_p1': 0, 'score_p2': 0,
        'round': 1, 'cards': {},
        'cards_submitted_p1': False, 'cards_submitted_p2': False,
        'location': None, 'location_name': None
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 Я Игрок 1", callback_data="become_p1"))
    markup.add(types.InlineKeyboardButton("Я Игрок 2", callback_data="join_p2"))
    markup.add(types.InlineKeyboardButton("▶️ Локация", callback_data="location_setup"))
    
    bot.send_message(message.chat.id, 
        f"🎮 <b>Игра создана!</b>\nВедущий: {escape_html(active_games[message.chat.id]['host_nickname'])}",
        reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=['r'])
def roll_short(message):
    if message.chat.type == 'private':
        return
    try:
        args = message.text.split()
        count = int(args[1]) if len(args) > 1 else 1
        if not (0 < count <= 20):
            bot.reply_to(message, "1-20")
            return
        results = [random.randint(1, 4) for _ in range(count)]
        bot.reply_to(message, f"🎲 {count}d4: {results}\n{'✅' if 4 in results else '❌'}")
    except:
        bot.reply_to(message, "/r число")

@bot.message_handler(commands=['s'])
def start_game_short(message):
    """Быстрый старт - ведущий не обязательно игрок"""
    if message.chat.type == 'private':
        bot.reply_to(message, "⚠️ Только в группах!")
        return
    if message.chat.id in active_games:
        bot.reply_to(message, "Игра уже идет!")
        return
    
    can_play, _ = check_limits(message.from_user.id)
    if not can_play:
        bot.reply_to(message, "Лимит боев!")
        return
    
    active_games[message.chat.id] = {
        'host': message.from_user.id,
        'host_nickname': get_user(message.from_user.id)[2] or message.from_user.first_name,
        'p1': None, 'nickname_p1': None,
        'p2': None, 'nickname_p2': None,
        'score_p1': 0, 'score_p2': 0,
        'round': 1, 'cards': {},
        'cards_submitted_p1': False, 'cards_submitted_p2': False,
        'location': None, 'location_name': None
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 Я Игрок 1", callback_data="quick_p1"))
    markup.add(types.InlineKeyboardButton("🎮 Я Игрок 2", callback_data="quick_p2"))
    markup.add(types.InlineKeyboardButton("▶️ Локация", callback_data="quick_location"))
    
    bot.send_message(message.chat.id, 
        f"🎮 <b>ИГРА СОЗДАНА!</b>\n\n"
        f"👤 Ведущий: {escape_html(active_games[message.chat.id]['host_nickname'])}\n\n"
        f"<b>Игроки:</b>\n"
        f"🎮 ⏳ Игрок 1\n"
        f"🎮 ⏳ Игрок 2\n\n"
        f"Нажмите кнопку чтобы стать игроком:", 
        reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=['join'])
def join_cmd(message):
    if message.chat.id not in active_games:
        return
    game = active_games[message.chat.id]
    if game['p2']:
        bot.reply_to(message, "Место занято!")
        return
    if message.from_user.id == game['p1']:
        bot.reply_to(message, "Вы Игрок 1!")
        return
    
    game['p2'] = message.from_user.id
    game['nickname_p2'] = get_user(message.from_user.id)[2] or message.from_user.first_name
    bot.reply_to(message, f"✅ Вы Игрок 2!")
    
    if game['p1'] and game['location_name']:
        bot.send_message(message.chat.id, 
            f"🎮 <b>ИГРА!</b>\n\n"
            f"👥 {escape_html(game['nickname_p1'])} vs {escape_html(game['nickname_p2'])}\n"
            f"📍 {escape_html(game['location_name'])}\n\n"
            f"📩 ЛС: <code>1,2: 2,0</code>",
            parse_mode="HTML")
        start_round(message.chat.id, game)

# --- ОБРАБОТЧИКИ КНОПОК ---

@bot.callback_query_handler(func=lambda call: call.data == "become_p1")
def become_p1(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if not game['p1']:
        game['p1'] = game['host']
        game['nickname_p1'] = game['host_nickname']
        bot.answer_callback_query(call.id, "Вы Игрок 1!")
        bot.send_message(call.message.chat.id, f"✅ {escape_html(game['nickname_p1'])} - Игрок 1!")
    else:
        bot.answer_callback_query(call.id, "Занято!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "join_p2")
def join_p2(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id == game['p1']:
        bot.answer_callback_query(call.id, "Вы Игрок 1!", show_alert=True)
        return
    if not game['p2']:
        game['p2'] = call.from_user.id
        game['nickname_p2'] = get_user(call.from_user.id)[2] or call.from_user.first_name
        bot.answer_callback_query(call.id, "Вы Игрок 2!")
        bot.send_message(call.message.chat.id, f"✅ {escape_html(game['nickname_p2'])} присоединился!")
    else:
        bot.answer_callback_query(call.id, "Занято!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "location_setup")
def location_setup(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎲 Случайная", callback_data="loc_random"))
    markup.add(types.InlineKeyboardButton("🚫 Без", callback_data="loc_none"))
    
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📍 Локация:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "loc_random")
def loc_random(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        return
    
    locs = get_locations()
    if locs:
        loc = random.choice(locs)
        game['location'] = loc[3]
        game['location_name'] = loc[0]
        if loc[3]:
            bot.send_photo(call.message.chat.id, loc[3], f"🎲 <b>{escape_html(loc[0])}</b>", parse_mode="HTML")
        check_and_start_game(call.message.chat.id, game)

@bot.callback_query_handler(func=lambda call: call.data == "loc_none")
def loc_none(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        return
    game['location'] = None
    game['location_name'] = "Без локации"
    bot.answer_callback_query(call.id, "Без локации")
    check_and_start_game(call.message.chat.id, game)

# --- КНОПКИ ДЛЯ /s ---

@bot.callback_query_handler(func=lambda call: call.data == "quick_p1")
def quick_p1(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if game['p1']:
        bot.answer_callback_query(call.id, "Занято!", show_alert=True)
        return
    game['p1'] = call.from_user.id
    game['nickname_p1'] = get_user(call.from_user.id)[2] or call.from_user.first_name
    bot.answer_callback_query(call.id, "Вы Игрок 1!")
    bot.send_message(call.message.chat.id, f"✅ {escape_html(game['nickname_p1'])} - Игрок 1!")
    check_quick_game_start(call.message.chat.id, game)

@bot.callback_query_handler(func=lambda call: call.data == "quick_p2")
def quick_p2(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id == game['p1']:
        bot.answer_callback_query(call.id, "Вы Игрок 1!", show_alert=True)
        return
    if game['p2']:
        bot.answer_callback_query(call.id, "Занято!", show_alert=True)
        return
    game['p2'] = call.from_user.id
    game['nickname_p2'] = get_user(call.from_user.id)[2] or call.from_user.first_name
    bot.answer_callback_query(call.id, "Вы Игрок 2!")
    bot.send_message(call.message.chat.id, f"✅ {escape_html(game['nickname_p2'])} - Игрок 2!")
    check_quick_game_start(call.message.chat.id, game)

@bot.callback_query_handler(func=lambda call: call.data == "quick_location")
def quick_location(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎲 Случайная", callback_data="quick_loc_random"))
    markup.add(types.InlineKeyboardButton("🚫 Без", callback_data="quick_loc_none"))
    
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📍 Локация:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "quick_loc_random")
def quick_loc_random(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        return
    
    locs = get_locations()
    if locs:
        loc = random.choice(locs)
        game['location'] = loc[3]
        game['location_name'] = loc[0]
        if loc[3]:
            bot.send_photo(call.message.chat.id, loc[3], f"🎲 <b>{escape_html(loc[0])}</b>", parse_mode="HTML")
        check_quick_game_start(call.message.chat.id, game)

@bot.callback_query_handler(func=lambda call: call.data == "quick_loc_none")
def quick_loc_none(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        return
    game['location'] = None
    game['location_name'] = "Без локации"
    bot.answer_callback_query(call.id, "Без локации")
    check_quick_game_start(call.message.chat.id, game)

def check_and_start_game(chat_id, game):
    if not game['p1'] or not game['p2'] or not game['location_name']:
        return
    
    bot.send_message(chat_id, 
        f"🎮 <b>СТАРТ!</b>\n\n"
        f"👥 {escape_html(game['nickname_p1'])} vs {escape_html(game['nickname_p2'])}\n"
        f"📍 {escape_html(game['location_name'])}\n\n"
        f"📩 ЛС: <code>1,2: 2,0</code>",
        parse_mode="HTML")
    
    start_round(chat_id, game)

def check_quick_game_start(chat_id, game):
    if not game['p1'] or not game['p2']:
        return
    if not game['location_name']:
        bot.send_message(chat_id, "⏳ Ждем выбора локации от ведущего...")
        return
    
    bot.send_message(chat_id, 
        f"🎮 <b>СТАРТ!</b>\n\n"
        f"👥 {escape_html(game['nickname_p1'])} vs {escape_html(game['nickname_p2'])}\n"
        f"📍 {escape_html(game['location_name'])}\n\n"
        f"📩 ЛС: <code>1,2: 2,0</code>",
        parse_mode="HTML")
    
    start_round(chat_id, game)

def start_round(chat_id, game):
    game['cards'] = {'p1': [], 'p2': []}
    game['cards_submitted_p1'] = False
    game['cards_submitted_p2'] = False
    
    bot.send_message(chat_id, 
        f"⚔️ <b>Раунд {game['round']}</b>\n"
        f"📊 {escape_html(game['nickname_p1'])} {game['score_p1']} : {escape_html(game['nickname_p2'])} {game['score_p2']}\n\n"
        f"📩 ЛС: <code>1,2: 2,0</code>",
        parse_mode="HTML")
# --- ОБРАБОТКА ОТПРАВКИ КАРТ (ТОЛЬКО ЛС) ---

@bot.message_handler(content_types=['text'])
def handle_card_submission(message):
    # ПРОВЕРКА: обрабатываем только в ЛС
    if message.chat.type != 'private':
        return
    
    user_id = message.from_user.id
    
    # Ищем активную игру где участвует пользователь
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
    
    if is_p1 and game['cards_submitted_p1']:
        bot.reply_to(message, "⚠️ Вы уже отправили карты!")
        return
    if is_p2 and game['cards_submitted_p2']:
        bot.reply_to(message, "⚠️ Вы уже отправили карты!")
        return
    
    text = message.text.strip()
    
    if ':' not in text:
        bot.reply_to(message, 
            "❌ Неверный формат!\n\n"
            "<b>Правильно:</b> <code>1,2: 2,0</code>\n"
            "(номера карт : способности)", 
            parse_mode="HTML")
        return
    
    try:
        parts = text.split(':')
        card_nums_str = parts[0].strip()
        abilities_str = parts[1].strip() if len(parts) > 1 else ""
        
        card_nums = [int(x.strip()) for x in card_nums_str.split(',') if x.strip().isdigit()]
        
        if not card_nums:
            bot.reply_to(message, "❌ Укажите карты!")
            return
        
        # ПРОВЕРКА: карты с "поддержка" НЕ считаются в лимите
        if len(card_nums) > 1:
            user_cards = get_user_cards(user_id)
            if is_friday():
                opponent_id = game['p2'] if is_p1 else game['p1']
                if opponent_id:
                    user_cards = get_user_cards(opponent_id)
            
            # Считаем только карты БЕЗ "поддержка"
            non_support_count = 0
            for cnum in card_nums:
                for cid, fid, cname in user_cards:
                    if cid == cnum:
                        if not cname.lower().endswith('поддержка'):
                            non_support_count += 1
                        break
            
            if non_support_count > 1:
                bot.reply_to(message, 
                    "❌ <b>Ошибка!</b>\n\n"
                    "Можно только 1 карту без 'поддержка'!\n"
                    "Карты с 'поддержка' не считаются в лимите.", 
                    parse_mode="HTML")
                return
        
        ability_details = [x.strip() for x in abilities_str.split(',')] if abilities_str else []
        
        user_cards = get_user_cards(user_id)
        if is_friday():
            opponent_id = game['p2'] if is_p1 else game['p1']
            if opponent_id:
                user_cards = get_user_cards(opponent_id)
        
        cards_data = []
        for idx, cnum in enumerate(card_nums):
            found = None
            for cid, fid, cname in user_cards:
                if cid == cnum:
                    found = (cid, fid, cname)
                    break
            
            if not found:
                bot.reply_to(message, f"❌ Карта #{cnum} не найдена!")
                return
            
            ab_text = ability_details[idx] if idx < len(ability_details) else "0"
            ab_num = 0
            details = ""
            for ch in ab_text:
                if ch.isdigit() and int(ch) in [0,1,2,3]:
                    ab_num = int(ch)
                    idx_ch = ab_text.index(ch) + 1
                    details = ab_text[idx_ch:].strip()
                    break
            
            cards_data.append({
                'file_id': found[1],
                'ability': ab_num,
                'details': details,
                'card_name': found[2],
                'card_id': found[0]
            })
        
        if is_p1:
            game['cards']['p1'] = cards_data
            game['cards_submitted_p1'] = True
            bot.reply_to(message, f"✅ Принято!\nКарт: {len(cards_data)}\nЖдем соперника...")
        else:
            game['cards']['p2'] = cards_data
            game['cards_submitted_p2'] = True
            bot.reply_to(message, f"✅ Принято!\nКарт: {len(cards_data)}\nЖдем соперника...")
        
        check_round_complete(found_chat, game)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

def check_round_complete(chat_id, game):
    if game['cards_submitted_p1'] and game['cards_submitted_p2']:
        reveal_cards(chat_id, game)

def reveal_cards(chat_id, game):
    p1_cards = game['cards']['p1']
    p2_cards = game['cards']['p2']
    
    media = []
    for card in p1_cards:
        cap = f"{escape_html(game['nickname_p1'])}\n🃏 {escape_html(card['card_name'])}\n⚡ {card['ability']}"
        if card['details']:
            cap += f"\n📝 {escape_html(card['details'])}"
        media.append(types.InputMediaPhoto(media=card['file_id'], caption=cap))
    
    for card in p2_cards:
        cap = f"{escape_html(game['nickname_p2'])}\n🃏 {escape_html(card['card_name'])}\n⚡ {card['ability']}"
        if card['details']:
            cap += f"\n📝 {escape_html(card['details'])}"
        media.append(types.InputMediaPhoto(media=card['file_id'], caption=cap))
    
    for i in range(0, len(media), 10):
        bot.send_media_group(chat_id, media[i:i+10])
    
    p1_sum = ", ".join([f"{escape_html(c['card_name'])} ({c['ability']})" for c in p1_cards])
    p2_sum = ", ".join([f"{escape_html(c['card_name'])} ({c['ability']})" for c in p2_cards])
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{game['nickname_p1']}", callback_data="win_p1"))
    markup.add(types.InlineKeyboardButton(f"{game['nickname_p2']}", callback_data="win_p2"))
    markup.add(types.InlineKeyboardButton("Ничья", callback_data="draw"))
    
    bot.send_message(chat_id, 
        f"<b>Раунд {game['round']}</b>\n\n"
        f"{escape_html(game['nickname_p1'])}: {p1_sum}\n"
        f"{escape_html(game['nickname_p2'])}: {p2_sum}\n\n"
        f"Ведущий, кто победил?",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("win_"))
def handle_win(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    winner = call.data.split("_")[1]
    if winner == 'p1':
        game['score_p1'] += 1
        wnick = game['nickname_p1']
    else:
        game['score_p2'] += 1
        wnick = game['nickname_p2']
    
    bot.answer_callback_query(call.id, f"{wnick} выиграл!")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    
    if game['score_p1'] >= 3 or game['score_p2'] >= 3:
        finish_game(call.message.chat.id, game)
    else:
        game['round'] += 1
        bot.send_message(call.message.chat.id, f"✅ {escape_html(wnick)} выиграл!\n📊 {game['score_p1']}:{game['score_p2']}")
        start_round(call.message.chat.id, game)

@bot.callback_query_handler(func=lambda call: call.data == "draw")
def handle_draw(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только ведущий!", show_alert=True)
        return
    
    game['draw_consent'] = {'p1': False, 'p2': False, 'host': True}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅", callback_data="agree_draw"))
    markup.add(types.InlineKeyboardButton("❌", callback_data="reject_draw"))
    bot.send_message(call.message.chat.id, "⚖️ Ничья? Согласитесь:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data in ["agree_draw", "reject_draw"])
def handle_draw_vote(call):
    if call.message.chat.id not in active_games:
        return
    game = active_games[call.message.chat.id]
    if call.from_user.id not in [game['p1'], game['p2']]:
        bot.answer_callback_query(call.id, "Только игроки!", show_alert=True)
        return
    
    if call.data == "agree_draw":
        if call.from_user.id == game['p1']:
            game['draw_consent']['p1'] = True
        else:
            game['draw_consent']['p2'] = True
    else:
        bot.send_message(call.message.chat.id, "❌ Отклонено")
        game['draw_consent'] = None
        reveal_cards(call.message.chat.id, game)
        return
    
    if all(game['draw_consent'].values()):
        finish_game_draw(call.message.chat.id, game)

def finish_game(chat_id, game):
    wnick = game['nickname_p1'] if game['score_p1'] >= 3 else game['nickname_p2']
    lnick = game['nickname_p2'] if game['score_p1'] >= 3 else game['nickname_p1']
    lscore = game['score_p2'] if game['score_p1'] >= 3 else game['score_p1']
    
    wcoins, lcoins = (3, 0) if lscore == 0 else (2, 1)
    
    wid = game['p1'] if game['score_p1'] >= 3 else game['p2']
    lid = game['p2'] if game['score_p1'] >= 3 else game['p1']
    
    wt, wr = update_user_stats(wid, wcoins, True, lid, won=True)
    lt, lr = update_user_stats(lid, lcoins, True, wid, won=False)
    
    today = datetime.date.today()
    limit = 14 if today.weekday() == 5 else 7
    
    text = (f"🏆 <b>КОНЕЦ!</b>\n\n"
            f"🥇 {escape_html(wnick)}\n📊 {game['score_p1']}:{game['score_p2']}\n\n"
            f"💰 {escape_html(wnick)}: +{wcoins} (Всего: {wt}, Осталось: {wr}/{limit})\n"
            f"💰 {escape_html(lnick)}: +{lcoins} (Всего: {lt}, Осталось: {lr}/{limit})")
    
    bot.send_message(chat_id, text, parse_mode="HTML")
    del active_games[chat_id]

def finish_game_draw(chat_id, game):
    p1t, p1r = update_user_stats(game['p1'], 1, True, game['p2'], draw=True)
    p2t, p2r = update_user_stats(game['p2'], 1, True, game['p1'], draw=True)
    
    today = datetime.date.today()
    limit = 14 if today.weekday() == 5 else 7
    
    text = (f"⚖️ <b>НИЧЬЯ!</b>\n\n"
            f"📊 {game['score_p1']}:{game['score_p2']}\n\n"
            f"💰 {escape_html(game['nickname_p1'])}: +1 (Всего: {p1t}, Осталось: {p1r}/{limit})\n"
            f"💰 {escape_html(game['nickname_p2'])}: +1 (Всего: {p2t}, Осталось: {p2r}/{limit})")
    
    bot.send_message(chat_id, text, parse_mode="HTML")
    del active_games[chat_id]

@bot.callback_query_handler(func=lambda call: call.data in ["accept_duel", "decline_duel"])
def handle_duel_response(call):
    if call.message.chat.id not in player_challenges:
        return
    
    chal = player_challenges[call.message.chat.id]
    if call.from_user.id != chal['target']:
        bot.answer_callback_query(call.id, "Только вызванный!", show_alert=True)
        return
    
    if call.data == "accept_duel":
        bot.answer_callback_query(call.id, "Принято!")
        del player_challenges[call.message.chat.id]
        
        active_games[call.message.chat.id] = {
            'host': chal['challenger'],
            'host_nickname': chal['challenger_nick'],
            'p1': chal['challenger'], 'nickname_p1': chal['challenger_nick'],
            'p2': chal['target'], 'nickname_p2': chal['target_nick'],
            'score_p1': 0, 'score_p2': 0, 'round': 1, 'cards': {},
            'cards_submitted_p1': False, 'cards_submitted_p2': False,
            'location': None, 'location_name': None
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎲 Случайная", callback_data="loc_random"))
        markup.add(types.InlineKeyboardButton("🚫 Без", callback_data="loc_none"))
        
        bot.send_message(call.message.chat.id, 
            f"✅ Дуэль!\n{escape_html(chal['challenger_nick'])} vs {escape_html(chal['target_nick'])}\n\n"
            f"Ведущий, выберите локацию:", 
            reply_markup=markup, parse_mode="HTML")
    else:
        bot.answer_callback_query(call.id, "Отклонено")
        bot.send_message(call.message.chat.id, f"❌ {escape_html(chal['target_nick'])} отклонил")
        del player_challenges[call.message.chat.id]
# --- БОЙ С БОССОМ ---

@bot.message_handler(commands=['boss_battle'])
def create_boss_battle(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_sunday():
        bot.reply_to(message, "⚠️ Только в воскресенье!")
        return
    
    if chat_id in boss_battles:
        bot.reply_to(message, "Битва уже создана!")
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
        "В 12:00 будет опрос\n"
        "Организатор получит уведомление в 8:00", 
        parse_mode="HTML")

@bot.message_handler(commands=['boss_time'])
def set_boss_time(message):
    username = message.from_user.username
    
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Только организатор и тестировщик!")
        return
    
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "❌ Укажите часы и минуты!\n\nИспользование: /boss_time <часы> <минуты>")
            return
        
        hours = int(args[1])
        minutes = int(args[2])
        
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            bot.reply_to(message, "Неверное время!")
            return
        
        chat_id = message.chat.id
        if chat_id in boss_battles:
            boss_battles[chat_id]['start_time'] = datetime.time(hours, minutes)
            boss_battles[chat_id]['organizer'] = message.from_user.id
            
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
        else:
            bot.reply_to(message, "❌ Сначала создайте битву с боссом командой /boss_battle")
    except (IndexError, ValueError):
        bot.reply_to(message, "Использование: /boss_time <часы> <минуты>")

@bot.message_handler(commands=['boss_reward'])
def boss_reward(message):
    """Награда от организатора или тестировщика"""
    username = message.from_user.username
    
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Только организатор и тестировщик!")
        return
    
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "❌ Укажите ID и монеты!\n\nИспользование: /boss_reward <ID> <монеты>")
            return
        
        target_id = int(args[1])
        coins = int(args[2])
        
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

# --- АДМИН-КОМАНДЫ ---

@bot.message_handler(commands=['test_mode'])
def test_mode(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Доступ запрещён")
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
    """Загрузить локацию (для организатора и тестировщика)"""
    username = message.from_user.username
    
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Только организатор и тестировщик!")
        return
    
    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "⚠️ Ответьте на фото локации этой командой")
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
    """Запланировать сообщение (для организатора и тестировщика)"""
    username = message.from_user.username
    
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Только организатор и тестировщик!")
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
                  message.from_user.id))
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
        
@bot.message_handler(commands=['dev_commands'])
def dev_commands(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    
    text = (f"🛠️ <b>DEV COMMANDS</b>\n\n"
            f"/test_mode — Режим теста\n"
            f"/upload_location — Загрузить локацию\n"
            f"/schedule_message — Запланировать сообщение\n"
            f"/boss_reward — Награда от босса\n"
            f"/boss_time — Время боя\n"
            f"/stats_user — Статистика игрока\n"
            f"/notifications — Уведомления\n"
            f"/add_coins — Добавить монеты\n"
            f"/reset_battles — Сбросить бои")
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['add_coins'])
def add_coins(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    
    try:
        target_id = int(message.text.split()[1])
        coins = int(message.text.split()[2])
        
        user = get_user(target_id)
        new_coins = user[3] + coins
        update_user(target_id, coins=new_coins)
        
        bot.reply_to(message, f"✅ Добавлено {coins} монет!\nБаланс: {new_coins}")
    except:
        bot.reply_to(message, "/add_coins ID монеты")

@bot.message_handler(commands=['reset_battles'])
def reset_battles(message):
    username = message.from_user.username
    if username not in ['angel_zam', ORGANIZER_USERNAME]:
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    
    try:
        target_id = int(message.text.split()[1])
        update_user(target_id, battles_today=0, last_play_date="")
        bot.reply_to(message, f"✅ Бои сброшены для {target_id}")
    except:
        bot.reply_to(message, "/reset_battles ID")
# --- ЕЖЕДНЕВНЫЕ СОБЫТИЯ ---

def setup_daily_events():
    """Настройка ежедневных событий по дням недели"""
    
    events = {
        'mon': "📅 <b>ПОНЕДЕЛЬНИК!</b>\n\nКомандные бои! Возможность проводить бои 2 на 2!!!",
        'tue': "📅 <b>ВТОРНИК!</b>\n\nТурнир в колизее! Победитель получит новую карту!",
        'wed': "📅 <b>СРЕДА!</b>\n\nОткрытие магазина! Покупка не случайных, а известных карт которые есть в наличии!",
        'thu': "📅 <b>ЧЕТВЕРГ!</b>\n\nРозыгрыш карты! Случайный игрок получает Серую карту!",
        'fri': "📅 <b>ПЯТНИЦА!</b>\n\nСмена сил! В этот день каждый из соперников использует набор карт своего противника!",
        'sat': "📅 <b>СУББОТА!</b>\n\nБезграничные бои! Количество оплачиваемых боев увеличивается до 14!!!",
        'sun': "📅 <b>ВОСКРЕСЕНЬЕ!</b>\n\nБОСС НЕДЕЛИ! Все участники объединяются и сражаются против босса недели ради Уникальных карт!"
    }
    
    for day, text in events.items():
        scheduler.add_job(
            lambda t=text: None,
            CronTrigger(day_of_week=day, hour=0, minute=0),
            id=f'{day}_event'
        )

# --- ЗАПУСК ---

if __name__ == '__main__':
    # Инициализация базы данных
    init_db()
    
    # Настройка ежедневных событий
    setup_daily_events()
    
    # Настройка команд меню
    setup_bot_commands()
    
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"📛 Организатор: @{ORGANIZER_USERNAME}")
    print(f"🧪 Тестировщик: @{TEST_MODE_USER}")
    print("=" * 50)
    print("⚠️ ВАЖНО: Попросите @Kitenokowo13 написать /start")
    print("   для автоматической регистрации как организатор!")
    print("=" * 50)
    print("✅ Бот готов к работе...")
    print("=" * 50)
    print("📋 Команды в группе: /duel, /list, /r, /s, /locations")
    print("📋 Команды в ЛС: /start, /name, /add, /my_cards, /delete, /surrender, /stats, /get_id")
    print("=" * 50)
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        scheduler.shutdown()
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        scheduler.shutdown()

