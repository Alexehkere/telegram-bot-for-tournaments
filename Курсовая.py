import psycopg2
import telebot
import pytz
from telebot import types
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.start()
from datetime import timedelta
# Подключение к базе данных
conn = psycopg2.connect(
    dbname="Alex",
    user="postgres",
    password="AnnaTorgashova0803",
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

# Инициализация бота
bot = telebot.TeleBot('7786218793:AAH2Qks8RMODaQfjiOpQMN5GTHEkljIaH3A')

# ID администратора
ADMIN_ID = 1296029280  # Замените на ваш ID

# Состояния пользователя
user_states = {}

# Константы для состояний
STATE_TOURNAMENT_CREATION = "tournament_creation"
STATE_TOURNAMENT_DELETION = "tournament_deletion"

# Создание таблиц
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    wins INT DEFAULT 0
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS tournaments (
    id SERIAL PRIMARY KEY,
    game_name TEXT NOT NULL,
    time TIMESTAMP NOT NULL,
    winner_id BIGINT REFERENCES users(user_id)
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS tournament_participants (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(tournament_id, user_id)
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS completed_tournaments (
    id SERIAL PRIMARY KEY,
    game_name TEXT NOT NULL,
    time TIMESTAMP NOT NULL,
    winner_id BIGINT REFERENCES users(user_id)
);
""")
# Таблица для команд и членов команд
cursor.execute("""
CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    leader_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS team_members (
    id SERIAL PRIMARY KEY,
    team_id INT REFERENCES teams(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(team_id, user_id)
);
""")
# Таблица для командных турниров
cursor.execute("""
CREATE TABLE IF NOT EXISTS team_tournaments (
    id SERIAL PRIMARY KEY,
    game_name TEXT NOT NULL,
    time TIMESTAMP NOT NULL
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS completed_team_tournaments (
    id SERIAL PRIMARY KEY,
    game_name TEXT NOT NULL,
    time TIMESTAMP NOT NULL,
    winner_team_id INT REFERENCES teams(id) ON DELETE CASCADE
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS team_tournament_participants (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES team_tournaments(id) ON DELETE CASCADE,
    team_id INT REFERENCES teams(id) ON DELETE CASCADE,
    UNIQUE (tournament_id, team_id)
);
""")
cursor.execute(""" 
CREATE TABLE IF NOT EXISTS team_requests (
    id SERIAL PRIMARY KEY,
    team_id INT REFERENCES teams(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending'  -- Возможные значения: 'pending', 'accepted', 'rejected'
);
""")
conn.commit()

# Функция для добавления пользователя в базу данных
def add_user_to_db(user_id, username):
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (user_id, username) VALUES (%s, %s)", (user_id, username))
            conn.commit()
    except Exception as e:
        print(f"Ошибка при добавлении пользователя в базу данных: {e}")

# Основное меню
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Создать турнир", "Удалить турнир", "Турниры", "Регистрация в турнире", "Лидеры", "Мой профиль")
    markup.add("Моя команда", "Мои турниры")  # Новая кнопка
    if ADMIN_ID:
        markup.add("Выбрать победителя для турнира")
    return markup

# Стартовая команда
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    username = message.from_user.username or "Неизвестный пользователь"
    add_user_to_db(user_id, username)
    bot.send_message(user_id, f"Привет, {username}! Ваш ID: {user_id}\nВыберите действие:", reply_markup=get_main_menu())

# Моя команда

@bot.message_handler(func=lambda message: message.text == "Моя команда")
def my_team(message):
    user_id = message.chat.id
    try:
        # Проверка, состоит ли пользователь в команде
        cursor.execute("""
        SELECT t.id, t.name, u.username AS leader 
        FROM teams t
        INNER JOIN users u ON t.leader_id = u.user_id
        INNER JOIN team_members tm ON t.id = tm.team_id
        WHERE tm.user_id = %s
        """, (user_id,))
        team = cursor.fetchone()

        if team:
            team_id, team_name, leader = team
            # Получение членов команды
            cursor.execute("""
            SELECT u.username FROM team_members tm
            INNER JOIN users u ON tm.user_id = u.user_id
            WHERE tm.team_id = %s
            """, (team_id,))
            members = cursor.fetchall()

            members_list = "\n".join([f"- {member[0]}" for member in members])
            response = f"Команда: {team_name}\nЛидер: {leader}\nУчастники:\n{members_list}"

            # Кнопки для лидера и участников
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            if leader == message.from_user.username:
                markup.add("Редактировать команду", "Удалить участника", "Удалить команду")
            markup.add("Выйти из команды", "Поиск команды", "Назад")
            markup.add("Поиск команды")  # Кнопка поиска
            bot.send_message(user_id, response, reply_markup=markup)
        else:
            # Если команды нет, предлагать создание или поиск
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("Создать команду", "Поиск команды", "Назад")
            bot.send_message(user_id, "Вы не состоите в команде. Вы можете создать свою команду или найти существующую.", reply_markup=markup)
    except Exception as e:
        bot.send_message(user_id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_join_"))
def confirm_join(call):
    team_id = int(call.data.split("_")[2])
    user_id = call.message.chat.id

    # Добавляем пользователя в команду
    cursor.execute("INSERT INTO team_members (team_id, user_id) VALUES (%s, %s)", (team_id, user_id))
    conn.commit()
    bot.send_message(user_id, "Вы успешно вступили в команду!", reply_markup=get_main_menu())


@bot.message_handler(func=lambda message: message.text == "Редактировать команду")
def edit_team(message):
    """Лидер может изменить лидера команды."""
    user_id = message.chat.id
    # Проверяем, является ли пользователь лидером команды
    cursor.execute("""
    SELECT t.id, t.name, t.leader_id
    FROM teams t
    INNER JOIN team_members tm ON tm.team_id = t.id
    WHERE tm.user_id = %s
    """, (user_id,))
    team = cursor.fetchone()

    if not team or team[2] != user_id:
        bot.send_message(user_id, "Вы не являетесь лидером команды.")
        return

    team_id, team_name, leader_id = team
    # Получаем всех участников команды, кроме лидера
    cursor.execute("""
    SELECT u.user_id, u.username FROM team_members tm
    INNER JOIN users u ON tm.user_id = u.user_id
    WHERE tm.team_id = %s AND tm.user_id != %s
    """, (team_id, leader_id))
    members = cursor.fetchall()

    if not members:
        bot.send_message(user_id, "В вашей команде нет других участников.")
        return

    markup = types.InlineKeyboardMarkup()
    for member_id, member_name in members:
        markup.add(types.InlineKeyboardButton(member_name, callback_data=f"change_leader_{team_id}_{member_id}"))

    bot.send_message(user_id, f"Выберите нового лидера команды {team_name}:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("change_leader_"))
def confirm_leader_change(call):
    team_id, new_leader_id = map(int, call.data.split("_")[1:])
    user_id = call.message.chat.id

    # Проверяем, является ли вызывающий лидером команды
    cursor.execute("""
    SELECT leader_id FROM teams WHERE id = %s
    """, (team_id,))
    current_leader = cursor.fetchone()[0]

    if current_leader != user_id:
        bot.answer_callback_query(call.id, "Вы не являетесь лидером этой команды.")
        return

    # Подтверждаем смену лидера
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Да", callback_data=f"confirm_leader_change_{team_id}_{new_leader_id}"),
        types.InlineKeyboardButton("Нет", callback_data=f"cancel_leader_change_{team_id}")
    )
    bot.send_message(user_id, "Вы уверены, что хотите сделать этого пользователя новым лидером?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_leader_change_"))
def execute_leader_change(call):
    team_id, new_leader_id = map(int, call.data.split("_")[1:])
    try:
        # Обновляем лидера команды
        cursor.execute("""
        UPDATE teams SET leader_id = %s WHERE id = %s
        """, (new_leader_id, team_id))
        conn.commit()
        bot.send_message(call.message.chat.id, f"Лидер команды успешно изменен.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при изменении лидера: {e}")

@bot.message_handler(func=lambda message: message.text == "Выйти из команды")
def leave_team(message):
    user_id = message.chat.id
    try:
        # Проверяем, состоит ли пользователь в команде
        cursor.execute("""
        SELECT tm.team_id, t.name 
        FROM team_members tm
        INNER JOIN teams t ON tm.team_id = t.id
        WHERE tm.user_id = %s
        """, (user_id,))

        team = cursor.fetchone()
        if not team:
            bot.send_message(user_id, "Вы не состоите в команде.")
            return

        team_id, team_name = team
        # Подтверждение выхода из команды
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("Подтвердить", callback_data=f"confirm_leave_team_{team_id}"),
            types.InlineKeyboardButton("Отменить", callback_data="cancel_leave_team")
        )
        bot.send_message(user_id, f"Вы уверены, что хотите выйти из команды '{team_name}'?", reply_markup=markup)

    except Exception as e:
        bot.send_message(user_id, f"Ошибка при попытке выйти из команды: {e}")
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_leave_team_"))
def confirm_leave_team(call):
    try:
        team_id = int(call.data.split("_")[3])
        user_id = call.message.chat.id

        # Удаляем пользователя из команды
        cursor.execute("DELETE FROM team_members WHERE team_id = %s AND user_id = %s", (team_id, user_id))
        conn.commit()
        bot.send_message(user_id, "Вы успешно вышли из команды.", reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(user_id, f"Ошибка при выходе из команды: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_leave_team")
def cancel_leave_team(call):
    bot.send_message(call.message.chat.id, "Выход из команды отменен.", reply_markup=get_main_menu())


from difflib import get_close_matches

@bot.message_handler(func=lambda message: message.text == "Поиск команды")
def search_team(message):
    user_id = message.chat.id

    # Проверяем, состоит ли пользователь в команде
    cursor.execute("SELECT team_id FROM team_members WHERE user_id = %s", (user_id,))
    if cursor.fetchone():
        bot.send_message(user_id, "Вы уже состоите в команде!", reply_markup=get_main_menu())
        return

    # Если пользователь не в команде, предлагаем ввести название для поиска
    bot.send_message(user_id, "Введите название команды для поиска:")
    user_states[user_id] = "searching_team"

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == "searching_team")
def handle_team_search(message):
    user_id = message.chat.id
    input_team_name = message.text.strip()

    try:
        # Поиск команды по названию
        cursor.execute("SELECT id, name, leader_id FROM teams WHERE name ILIKE %s", (f"%{input_team_name}%",))
        team = cursor.fetchone()

        if team:
            team_id, team_name, leader_id = team
            # Отправка заявки лидеру
            markup = types.InlineKeyboardMarkup()
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("Принять", callback_data=f"accept_request_{team_id}_{user_id}"),
                types.InlineKeyboardButton("Отклонить", callback_data=f"reject_request_{team_id}_{user_id}")

            )
            bot.send_message(leader_id, f"Пользователь @{message.from_user.username} хочет вступить в вашу команду '{team_name}'.",
                             reply_markup=markup)

            # Сохранение заявки
            cursor.execute("""
                INSERT INTO team_requests (team_id, user_id, status) VALUES (%s, %s, 'pending')
            """, (team_id, user_id))
            conn.commit()

            bot.send_message(user_id, f"Заявка отправлена лидеру команды '{team_name}'.", reply_markup=get_main_menu())
        else:
            bot.send_message(user_id, "Команда не найдена. Попробуйте снова.", reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(user_id, f"Ошибка: {e}")
    finally:
        user_states.pop(user_id, None)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("accept_request_", "reject_request_")))
def handle_request(call):
    try:
        print(f"Получен callback_data: {call.data}")  # Логируем для отладки

        # Определяем действие
        if call.data.startswith("accept_request_"):
            action = "accept"
        elif call.data.startswith("reject_request_"):
            action = "reject"
        else:
            raise ValueError(f"Неизвестное действие в callback_data: {call.data}")

        # Извлекаем данные после префикса
        data = call.data.split(f"{action}_request_")[1]
        team_id, user_id = map(int, data.split("_"))

        # Обработка действия
        if action == "accept":
            accept_team_request(call, team_id, user_id)
        elif action == "reject":
            reject_team_request(call, team_id, user_id)
    except ValueError as e:
        bot.send_message(call.message.chat.id, f"Ошибка обработки callback_data: {e}")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Общая ошибка: {e}")





@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_team_"))
def confirm_suggested_team(call):
    suggested_name = call.data.split("_")[2]
    bot.answer_callback_query(call.id)
    search_team(bot.send_message(call.message.chat.id, suggested_name))

@bot.callback_query_handler(func=lambda call: call.data == "decline_team_search")
def decline_suggested_team(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Поиск отменен. Попробуйте снова.", reply_markup=get_main_menu())



@bot.message_handler(func=lambda message: message.text == "Редактировать команду")
def edit_team(message):
    """Лидер может изменить лидера команды."""
    user_id = message.chat.id
    # Проверяем, является ли пользователь лидером команды
    cursor.execute("""
    SELECT t.id, t.name, t.leader_id
    FROM teams t
    INNER JOIN team_members tm ON tm.team_id = t.id
    WHERE tm.user_id = %s
    """, (user_id,))
    team = cursor.fetchone()

    if not team or team[2] != user_id:
        bot.send_message(user_id, "Вы не являетесь лидером команды.")
        return

    team_id, team_name, leader_id = team
    # Получаем всех участников команды, кроме лидера
    cursor.execute("""
    SELECT u.user_id, u.username FROM team_members tm
    INNER JOIN users u ON tm.user_id = u.user_id
    WHERE tm.team_id = %s AND tm.user_id != %s
    """, (team_id, leader_id))
    members = cursor.fetchall()

    if not members:
        bot.send_message(user_id, "В вашей команде нет других участников.")
        return

    markup = types.InlineKeyboardMarkup()
    for member_id, member_name in members:
        markup.add(types.InlineKeyboardButton(member_name, callback_data=f"change_leader_{team_id}_{member_id}"))

    bot.send_message(user_id, f"Выберите нового лидера команды {team_name}:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Удалить команду")
def delete_team(message):
    user_id = message.chat.id
    # Проверяем, является ли пользователь лидером команды
    cursor.execute("""
    SELECT id, name FROM teams WHERE leader_id = %s
    """, (user_id,))
    team = cursor.fetchone()

    if not team:
        bot.send_message(user_id, "Вы не являетесь лидером команды.")
        return

    team_id, team_name = team
    # Подтверждение удаления команды
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Подтвердить", callback_data=f"confirm_delete_team_{team_id}"),
        types.InlineKeyboardButton("Отменить", callback_data="cancel_delete_team")
    )
    bot.send_message(user_id, f"Вы уверены, что хотите удалить команду {team_name}?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_team_"))
def confirm_delete_team(call):
    team_id = int(call.data.split("_")[3])
    try:
        # Удаляем связанные записи в completed_team_tournaments
        cursor.execute("DELETE FROM completed_team_tournaments WHERE winner_team_id = %s", (team_id,))

        # Затем удаляем саму команду
        cursor.execute("DELETE FROM teams WHERE id = %s", (team_id,))
        conn.commit()
        bot.send_message(call.message.chat.id, "Команда успешно удалена.", reply_markup=get_main_menu())
    except Exception as e:
        conn.rollback()  # Откат изменений в случае ошибки
        bot.send_message(call.message.chat.id, f"Ошибка при удалении команды: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete_team")
def cancel_delete_team(call):
    bot.send_message(call.message.chat.id, "Удаление команды отменено.", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "Создать команду")
def create_team(message):
    user_id = message.chat.id
    try:
        # Проверка, состоит ли пользователь уже в команде
        cursor.execute("""
        SELECT team_id FROM team_members WHERE user_id = %s
        """, (user_id,))
        if cursor.fetchone():
            bot.send_message(user_id, "Вы уже состоите в команде!")
            return

        # Сохранение состояния для ввода названия
        user_states[user_id] = "creating_team"
        bot.send_message(user_id, "Введите название команды:")
    except Exception as e:
        bot.send_message(user_id, f"Ошибка: {e}")

#Создание команды
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == "creating_team")
def save_team(message):
    user_id = message.chat.id
    team_name = message.text.strip()
    try:
        # Создаем команду
        cursor.execute("""
        INSERT INTO teams (name, leader_id) VALUES (%s, %s) RETURNING id
        """, (team_name, user_id))
        team_id = cursor.fetchone()[0]
        cursor.execute("""
        INSERT INTO team_members (team_id, user_id) VALUES (%s, %s)
        """, (team_id, user_id))
        conn.commit()
        user_states.pop(user_id)
        bot.send_message(user_id, f"Команда '{team_name}' успешно создана!", reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(user_id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == "Найти команду")
def find_team(message):
    user_id = message.chat.id
    try:
        # Проверка, состоит ли пользователь уже в команде
        cursor.execute("""
        SELECT team_id FROM team_members WHERE user_id = %s
        """, (user_id,))
        if cursor.fetchone():
            bot.send_message(user_id, "Вы уже состоите в команде!", reply_markup=get_main_menu())
            return

        # Сохранение состояния для ввода названия
        user_states[user_id] = "searching_team"
        bot.send_message(user_id, "Введите название команды:")
    except Exception as e:
        bot.send_message(user_id, f"Ошибка: {e}")

    @bot.message_handler(func=lambda message: user_states.get(message.chat.id) == "searching_team")
    def search_team(message):
        user_id = message.chat.id
        team_name = message.text.strip()

        try:
            # Поиск команды
            cursor.execute("""
            SELECT id, name, leader_id FROM teams WHERE name ILIKE %s
            """, (f"%{team_name}%",))
            team = cursor.fetchone()

            if team:
                team_id, team_name, leader_id = team
                cursor.execute("SELECT username FROM users WHERE user_id = %s", (leader_id,))
                leader_name = cursor.fetchone()[0]

                # Отправка заявки лидеру
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("Принять", callback_data=f"accept_team_{team_id}_{user_id}"),
                    types.InlineKeyboardButton("Отклонить", callback_data=f"reject_team_{team_id}_{user_id}")
                )
                bot.send_message(leader_id, f"Пользователь @{message.from_user.username} хочет вступить в вашу команду '{team_name}'.",
                                reply_markup=markup)
                bot.send_message(user_id, f"Заявка отправлена лидеру команды '{team_name}'.", reply_markup=get_main_menu())
            else:
                bot.send_message(user_id, "Команда не найдена. Попробуйте снова.", reply_markup=get_main_menu())
        except Exception as e:
            bot.send_message(user_id, f"Ошибка: {e}")

    #сообщение лидеру
    def team_request_markup(team_id, user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("Принять", callback_data=f"accept_team_{team_id}_{user_id}"),
            types.InlineKeyboardButton("Отклонить", callback_data=f"reject_team_{team_id}_{user_id}")
        )
        return markup


@bot.callback_query_handler(func=lambda call: call.data.startswith(("accept_request_", "reject_request_")))
def handle_request(call):
    try:
        print(f"Получен callback_data: {call.data}")  # Логируем данные для отладки

        # Разбиваем callback_data
        data_parts = call.data.split("_")

        # Проверяем структуру данных
        if len(data_parts) != 3:
            bot.send_message(call.message.chat.id, f"Ошибка: недостаточно данных в callback_data: {call.data}")
            return

        action, team_id, user_id = data_parts[0], data_parts[1], data_parts[2]

        # Проверяем, что team_id и user_id — числа
        if not team_id.isdigit() or not user_id.isdigit():
            bot.send_message(call.message.chat.id, f"Ошибка: некорректные ID в callback_data: {call.data}")
            return

        team_id, user_id = int(team_id), int(user_id)

        # Обработка действия
        if action == "accept_request":
            accept_team_request(call, team_id, user_id)
        elif action == "reject_request":
            reject_team_request(call, team_id, user_id)
        else:
            bot.send_message(call.message.chat.id, f"Ошибка: неизвестное действие {action}")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Общая ошибка: {e}")


def accept_team_request(call, team_id, user_id):
    try:
        # Проверка заявки
        cursor.execute("""
            SELECT id FROM team_requests 
            WHERE team_id = %s AND user_id = %s AND status = 'pending'
        """, (team_id, user_id))
        request = cursor.fetchone()

        if not request:
            bot.answer_callback_query(call.id, "Заявка уже обработана.")
            return

        # Обновление статуса заявки
        cursor.execute("""
            UPDATE team_requests SET status = 'accepted' 
            WHERE team_id = %s AND user_id = %s
        """, (team_id, user_id))

        # Добавление пользователя в команду
        cursor.execute("""
            INSERT INTO team_members (team_id, user_id) VALUES (%s, %s)
        """, (team_id, user_id))
        conn.commit()

        bot.send_message(user_id, "Ваша заявка на вступление в команду одобрена!", reply_markup=get_main_menu())
        bot.send_message(call.message.chat.id, "Пользователь успешно добавлен в команду.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при одобрении заявки: {e}")


def reject_team_request(call, team_id, user_id):
    try:
        # Обновление статуса заявки
        cursor.execute("""
            UPDATE team_requests SET status = 'rejected' 
            WHERE team_id = %s AND user_id = %s
        """, (team_id, user_id))
        conn.commit()

        bot.send_message(user_id, "Ваша заявка на вступление в команду отклонена.", reply_markup=get_main_menu())
        bot.send_message(call.message.chat.id, "Заявка отклонена.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при отклонении заявки: {e}")



@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_team_"))
def confirm_suggested_team(call):
    suggested_name = call.data.split("_")[2]
    bot.answer_callback_query(call.id)
    search_team(bot.send_message(call.message.chat.id, suggested_name))

@bot.callback_query_handler(func=lambda call: call.data == "decline_team_search")
def decline_suggested_team(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Поиск отменен. Попробуйте снова.", reply_markup=get_main_menu())

# Мой профиль
@bot.message_handler(func=lambda message: message.text == "Мой профиль")
def show_profile(message):
    user_id = message.chat.id
    try:
        # Получение данных профиля
        cursor.execute("SELECT username, wins FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        username, wins = user if user else ("Неизвестный", 0)

        # Получение аватарки пользователя
        user_profile = bot.get_chat(user_id)
        profile_photo = bot.get_user_profile_photos(user_id, limit=1)
        avatar = profile_photo.photos[0][-1].file_id if profile_photo.total_count > 0 else None

        # Состоит ли пользователь в команде
        cursor.execute("""
        SELECT t.name, CASE WHEN t.leader_id = %s THEN 'Лидер' ELSE 'Участник' END AS role
        FROM team_members tm
        INNER JOIN teams t ON tm.team_id = t.id
        WHERE tm.user_id = %s
        """, (user_id, user_id))
        team_info = cursor.fetchone()

        if team_info:
            team_name, role = team_info
            team_status = f"Состоите в команде: {team_name} (Роль: {role})"
        else:
            team_status = "Не состоите в команде."

        response = f"Профиль:\nИмя: {username}\nПобеды: {wins}\n{team_status}"

        # Если есть аватарка, отправляем с ней
        if avatar:
            bot.send_photo(user_id, avatar, caption=response)
        else:
            bot.send_message(user_id, response)
    except Exception as e:
        bot.send_message(user_id, f"Ошибка при получении профиля: {e}")

#Редактировать команду

@bot.message_handler(func=lambda message: message.text == "Редактировать команду")
def edit_team(message):
    """Лидер может изменить лидера команды."""
    user_id = message.chat.id
    # Проверяем, является ли пользователь лидером команды
    cursor.execute("""
    SELECT t.id, t.name, t.leader_id
    FROM teams t
    INNER JOIN team_members tm ON tm.team_id = t.id
    WHERE tm.user_id = %s
    """, (user_id,))
    team = cursor.fetchone()

    if not team or team[2] != user_id:
        bot.send_message(user_id, "Вы не являетесь лидером команды.")
        return

    team_id, team_name, leader_id = team
    # Получаем всех участников команды, кроме лидера
    cursor.execute("""
    SELECT u.user_id, u.username FROM team_members tm
    INNER JOIN users u ON tm.user_id = u.user_id
    WHERE tm.team_id = %s AND tm.user_id != %s
    """, (team_id, leader_id))
    members = cursor.fetchall()

    if not members:
        bot.send_message(user_id, "В вашей команде нет других участников.")
        return

    markup = types.InlineKeyboardMarkup()
    for member_id, member_name in members:
        markup.add(types.InlineKeyboardButton(member_name, callback_data=f"change_leader_{team_id}_{member_id}"))

    bot.send_message(user_id, f"Выберите нового лидера команды {team_name}:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("change_leader_"))
    def confirm_leader_change(call):
        team_id, new_leader_id = map(int, call.data.split("_")[1:])
        user_id = call.message.chat.id

        # Проверяем, является ли вызывающий лидером команды
        cursor.execute("""
           SELECT leader_id FROM teams WHERE id = %s
           """, (team_id,))
        current_leader = cursor.fetchone()[0]

        if current_leader != user_id:
            bot.answer_callback_query(call.id, "Вы не являетесь лидером этой команды.")
            return

        # Подтверждаем смену лидера
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("Да", callback_data=f"confirm_leader_change_{team_id}_{new_leader_id}"),
            types.InlineKeyboardButton("Нет", callback_data=f"cancel_leader_change_{team_id}")
        )
        bot.send_message(user_id, "Вы уверены, что хотите сделать этого пользователя новым лидером?",
                         reply_markup=markup)

        @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_leader_change_"))
        def execute_leader_change(call):
            team_id, new_leader_id = map(int, call.data.split("_")[1:])
            try:
                # Обновляем лидера команды
                cursor.execute("""
                   UPDATE teams SET leader_id = %s WHERE id = %s
                   """, (new_leader_id, team_id))
                conn.commit()
                bot.send_message(call.message.chat.id, f"Лидер команды успешно изменен.")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Ошибка при изменении лидера: {e}")


@bot.message_handler(func=lambda message: message.text == "Удалить участника")
def remove_member(message):
    user_id = message.chat.id
    try:
        # Проверка, является ли пользователь лидером команды
        cursor.execute("""
        SELECT id FROM teams WHERE leader_id = %s
        """, (user_id,))
        team = cursor.fetchone()
        if not team:
            bot.send_message(user_id, "Вы не являетесь лидером команды.")
            return

        team_id = team[0]
        # Получение участников
        cursor.execute("""
        SELECT u.user_id, u.username FROM team_members tm
        INNER JOIN users u ON tm.user_id = u.user_id
        WHERE tm.team_id = %s AND u.user_id != %s
        """, (team_id, user_id))
        members = cursor.fetchall()

        if not members:
            bot.send_message(user_id, "В команде нет других участников.")
            return

        # Кнопки для выбора участника
        markup = types.InlineKeyboardMarkup()
        for member_id, member_name in members:
            markup.add(types.InlineKeyboardButton(member_name, callback_data=f"remove_{team_id}_{member_id}"))
        bot.send_message(user_id, "Выберите участника для удаления:", reply_markup=markup)
    except Exception as e:
        bot.send_message(user_id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_"))
def confirm_remove_member(call):
    _, team_id, member_id = call.data.split("_")
    try:
        cursor.execute("""
        DELETE FROM team_members WHERE team_id = %s AND user_id = %s
        """, (team_id, member_id))
        conn.commit()
        bot.send_message(call.message.chat.id, "Участник успешно удален из команды.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")


# Установка победителя
@bot.message_handler(func=lambda message: message.text == "Выбрать победителя для турнира")
def set_winner(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Победитель одиночного турнира", "Победитель командного турнира")
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите тип турнира:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "Победитель командного турнира")
def set_team_tournament_winner(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.")
        return

    try:
        cursor.execute("SELECT id, game_name FROM team_tournaments")
        tournaments = cursor.fetchall()
        if not tournaments:
            bot.send_message(message.chat.id, "Нет доступных командных турниров для выбора победителя.")
            return

        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name in tournaments:
            markup.add(types.InlineKeyboardButton(f"{game_name}", callback_data=f"setwinner_team_{tournament_id}"))
        bot.send_message(message.chat.id, "Выберите командный турнир для установки победителя:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("setwinner_team_"))
def choose_team_winner(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    tournament_id = int(call.data.split("_")[2])
    try:
        # Получаем список команд-участников
        cursor.execute("""
            SELECT ttp.team_id, t.name 
            FROM team_tournament_participants ttp
            INNER JOIN teams t ON ttp.team_id = t.id
            WHERE ttp.tournament_id = %s
        """, (tournament_id,))
        teams = cursor.fetchall()

        if not teams:
            bot.send_message(call.message.chat.id, "Нет участников в данном командном турнире.")
            return

        markup = types.InlineKeyboardMarkup()
        for team_id, team_name in teams:
            markup.add(
                types.InlineKeyboardButton(f"{team_name}", callback_data=f"winner_team_{tournament_id}_{team_id}")
            )
        bot.send_message(call.message.chat.id, "Выберите победителя:", reply_markup=markup)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("winner_team_"))
def finalize_team_winner(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    tournament_id, team_id = map(int, call.data.split("_")[2:])
    try:
        # Получаем данные турнира
        cursor.execute("SELECT game_name, time FROM team_tournaments WHERE id = %s", (tournament_id,))
        tournament = cursor.fetchone()

        if tournament:
            game_name, time = tournament

            # Сохраняем данные в завершённые командные турниры
            cursor.execute("""
                INSERT INTO completed_team_tournaments (game_name, time, winner_team_id) 
                VALUES (%s, %s, %s)
            """, (game_name, time, team_id))

            # Удаляем турнир
            cursor.execute("DELETE FROM team_tournaments WHERE id = %s", (tournament_id,))
            conn.commit()
            bot.send_message(call.message.chat.id, "Победитель успешно установлен, командный турнир завершён.")
    except Exception as e:
        conn.rollback()
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

#Победитель одиноного турнира
@bot.message_handler(func=lambda message: message.text == "Победитель одиночного турнира")
def set_winner_for_tournament(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.")
        return

    try:
        cursor.execute("SELECT id, game_name FROM tournaments WHERE winner_id IS NULL")
        tournaments = cursor.fetchall()
        if not tournaments:
            bot.send_message(message.chat.id, "Нет доступных одиночных турниров для выбора победителя.")
            return

        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name in tournaments:
            markup.add(types.InlineKeyboardButton(f"{game_name}", callback_data=f"setwinner_{tournament_id}"))
        bot.send_message(message.chat.id, "Выберите одиночный турнир для установки победителя:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("setwinner_"))
def choose_winner_for_tournament(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    tournament_id = int(call.data.split("_")[1])
    try:
        cursor.execute("""
            SELECT tp.user_id, u.username 
            FROM tournament_participants tp
            INNER JOIN users u ON tp.user_id = u.user_id
            WHERE tp.tournament_id = %s
        """, (tournament_id,))
        participants = cursor.fetchall()

        if not participants:
            bot.send_message(call.message.chat.id, "Нет участников в данном одиночном турнире.")
            return

        markup = types.InlineKeyboardMarkup()
        for user_id, username in participants:
            markup.add(
                types.InlineKeyboardButton(f"{username}", callback_data=f"winner_{tournament_id}_{user_id}")
            )
        bot.send_message(call.message.chat.id, "Выберите победителя:", reply_markup=markup)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("winner_"))
def finalize_winner_for_tournament(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    tournament_id, user_id = map(int, call.data.split("_")[1:])
    try:
        # Получаем данные турнира
        cursor.execute("SELECT game_name, time FROM tournaments WHERE id = %s", (tournament_id,))
        tournament = cursor.fetchone()

        if tournament:
            game_name, time = tournament

            # Сохраняем данные в завершённые турниры
            cursor.execute("""
                INSERT INTO completed_tournaments (game_name, time, winner_id) 
                VALUES (%s, %s, %s)
            """, (game_name, time, user_id))

            # Увеличиваем счётчик побед
            cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = %s", (user_id,))

            # Удаляем турнир
            cursor.execute("DELETE FROM tournaments WHERE id = %s", (tournament_id,))
            conn.commit()
            bot.send_message(call.message.chat.id, "Победитель успешно установлен, одиночный турнир завершён.")
    except Exception as e:
        conn.rollback()
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")



# Регистрация в турнире
@bot.message_handler(func=lambda message: message.text == "Регистрация в турнире")
def register_tournament_type(message):
    """Выбор типа турнира для регистрации."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Одиночные турниры", "Командные турниры")
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите тип турнира для регистрации:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Одиночные турниры")
def register_single_tournament(message):
    """Вывод списка одиночных турниров для регистрации."""
    try:
        cursor.execute("SELECT id, game_name, time FROM tournaments WHERE winner_id IS NULL")
        tournaments = cursor.fetchall()
        if not tournaments:
            bot.send_message(message.chat.id, "На данный момент нет доступных одиночных турниров.", reply_markup=get_main_menu())
            return

        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name, time in tournaments:
            markup.add(
                types.InlineKeyboardButton(
                    f"{game_name} ({time})",
                    callback_data=f"register_single_{tournament_id}"
                )
            )
        bot.send_message(message.chat.id, "Выберите одиночный турнир для регистрации:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при получении списка одиночных турниров: {e}")

@bot.message_handler(func=lambda message: message.text == "Командные турниры")
def register_team_tournament(message):
    """Вывод списка командных турниров для регистрации."""
    try:
        cursor.execute("SELECT id, game_name, time FROM team_tournaments")
        tournaments = cursor.fetchall()
        if not tournaments:
            bot.send_message(message.chat.id, "На данный момент нет доступных командных турниров.", reply_markup=get_main_menu())
            return

        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name, time in tournaments:
            markup.add(
                types.InlineKeyboardButton(
                    f"{game_name} ({time})",
                    callback_data=f"register_team_{tournament_id}"
                )
            )
        bot.send_message(message.chat.id, "Выберите командный турнир для регистрации:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при получении списка командных турниров: {e}")

# Обработка регистрации на одиночный турнир
@bot.callback_query_handler(func=lambda call: call.data.startswith("register_single_"))
def handle_single_registration(call):
    try:
        tournament_id = int(call.data.split("_")[2])
        user_id = call.message.chat.id

        # Проверяем, есть ли свободные места
        cursor.execute(
            "SELECT COUNT(*) FROM tournament_participants WHERE tournament_id = %s",
            (tournament_id,)
        )
        participant_count = cursor.fetchone()[0]
        if participant_count >= 10:
            bot.answer_callback_query(call.id, "Этот турнир уже заполнен.")
            return

        # Проверяем, зарегистрирован ли пользователь
        cursor.execute(
            "SELECT * FROM tournament_participants WHERE tournament_id = %s AND user_id = %s",
            (tournament_id, user_id)
        )
        if cursor.fetchone():
            bot.answer_callback_query(call.id, "Вы уже зарегистрированы в этом турнире.")
            return

        # Регистрируем пользователя
        cursor.execute(
            "INSERT INTO tournament_participants (tournament_id, user_id) VALUES (%s, %s)",
            (tournament_id, user_id)
        )
        conn.commit()
        bot.answer_callback_query(call.id, "Вы успешно зарегистрированы в турнире!")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка при регистрации: {e}")

# Обработка регистрации на командный турнир
@bot.callback_query_handler(func=lambda call: call.data.startswith("register_team_"))
def handle_team_registration(call):
    """Регистрация команды на командный турнир."""
    try:
        tournament_id = int(call.data.split("_")[2])
        user_id = call.message.chat.id

        # Проверяем, состоит ли пользователь в команде
        cursor.execute("""
            SELECT tm.team_id, t.name 
            FROM team_members tm
            INNER JOIN teams t ON tm.team_id = t.id
            WHERE tm.user_id = %s
        """, (user_id,))
        team = cursor.fetchone()
        if not team:
            bot.answer_callback_query(call.id, "Вы не состоите в команде. Регистрация невозможна.")
            return

        team_id, team_name = team

        # Проверяем, зарегистрирована ли команда в турнире
        cursor.execute("""
            SELECT * FROM team_tournament_participants 
            WHERE tournament_id = %s AND team_id = %s
        """, (tournament_id, team_id))
        if cursor.fetchone():
            bot.answer_callback_query(call.id, f"Команда '{team_name}' уже зарегистрирована на этот турнир.")
            return

        # Регистрируем команду в турнире
        cursor.execute("""
            INSERT INTO team_tournament_participants (tournament_id, team_id) 
            VALUES (%s, %s)
        """, (tournament_id, team_id))
        conn.commit()
        bot.answer_callback_query(call.id, f"Команда '{team_name}' успешно зарегистрирована в турнире!")
    except Exception as e:
        conn.rollback()  # Откат транзакции при ошибке
        bot.answer_callback_query(call.id, f"Ошибка при регистрации команды: {e}")



# Установка победителя
@bot.message_handler(func=lambda message: message.text == "Лидеры")
def leaders_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Лидеры участников", "Лидеры команд")
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите категорию лидеров:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Лидеры участников")
def show_participant_leaders(message):
    try:
        cursor.execute("""
        SELECT username, wins FROM users WHERE wins > 0 ORDER BY wins DESC LIMIT 10
        """)
        leaders = cursor.fetchall()

        if leaders:
            response = "Лидеры участников:\n"
            for username, wins in leaders:
                response += f"{username}: {wins} побед\n"
        else:
            response = "Нет данных о победителях."
        bot.send_message(message.chat.id, response)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == "Лидеры команд")
def show_team_leaders(message):
    try:
        cursor.execute("""
            SELECT t.name, u.username AS leader, COUNT(ctt.id) AS wins, COUNT(tm.user_id) AS members_count
            FROM teams t
            INNER JOIN users u ON t.leader_id = u.user_id
            LEFT JOIN completed_team_tournaments ctt ON ctt.winner_team_id = t.id
            LEFT JOIN team_members tm ON t.id = tm.team_id
            GROUP BY t.id, u.username
            ORDER BY wins DESC, members_count DESC
        """)
        leaders = cursor.fetchall()

        if leaders:
            response = "Лидеры команд:\n"
            for team_name, leader, wins, members_count in leaders:
                response += f"Команда: {team_name}, Лидер: {leader}, Победы: {wins}, Участников: {members_count}\n"
        else:
            response = "Нет данных о командах."
        bot.send_message(message.chat.id, response)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")


@bot.message_handler(func=lambda message: message.text == "Мой профиль")
def show_profile(message):
    try:
        user_id = message.chat.id
        cursor.execute("SELECT wins FROM users WHERE user_id = %s", (user_id,))
        wins = cursor.fetchone()[0]

        cursor.execute("""
        SELECT t.game_name, t.time, 
                CASE WHEN t.winner_id = %s THEN 'Победа' ELSE 'Участие' END AS status
        FROM tournament_participants tp
        INNER JOIN tournaments t ON tp.tournament_id = t.id
        WHERE tp.user_id = %s

        UNION ALL

        SELECT ct.game_name, ct.time, 'Победа' AS status
        FROM completed_tournaments ct
        WHERE ct.winner_id = %s
        """, (user_id, user_id, user_id))
        tournaments = cursor.fetchall()

        response = f"Ваш профиль:\nПобеды: {wins}\nТурниры:\n"
        for game_name, time, status in tournaments:
            response += f"{game_name} ({time}) — {status}\n"
        bot.send_message(message.chat.id, response)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при получении профиля: {e}")

# Установка победителя
@bot.message_handler(func=lambda message: message.text == "Установить победителя" and message.chat.id == ADMIN_ID)
def set_winner(message):
    try:
        cursor.execute("SELECT id, game_name FROM tournaments WHERE winner_id IS NULL")
        tournaments = cursor.fetchall()
        if not tournaments:
            bot.send_message(message.chat.id, "Нет доступных турниров для выбора победителя.")
            return

        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name in tournaments:
            markup.add(types.InlineKeyboardButton(f"{game_name}", callback_data=f"setwinner_{tournament_id}"))
        bot.send_message(message.chat.id, "Выберите турнир для установки победителя:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

#   Обработка выбора победителя
    @bot.callback_query_handler(func=lambda call: call.data.startswith("setwinner_"))
    def choose_winner(call):
        if call.message.chat.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "У вас нет прав для установки победителя.")
            return
        tournament_id = int(call.data.split("_")[1])
        try:
            cursor.execute("""
            SELECT tp.user_id, u.username 
            FROM tournament_participants tp
            INNER JOIN users u ON tp.user_id = u.user_id
            WHERE tp.tournament_id = %s
            """, (tournament_id,))
            participants = cursor.fetchall()

            if not participants:
                bot.send_message(call.message.chat.id, "Нет участников в данном турнире.")
            return

            markup = types.InlineKeyboardMarkup()
            for user_id, username in participants:
                markup.add(
                    types.InlineKeyboardButton(f"{username}", callback_data=f"winner_{tournament_id}_{user_id}"))
            bot.send_message(call.message.chat.id, "Выберите победителя:", reply_markup=markup)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка: {e}")

        # Установка победителя
        @bot.callback_query_handler(func=lambda call: call.data.startswith("winner_"))
        def finalize_winner(call):
            if call.message.chat.id != ADMIN_ID:
                bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
                return
            tournament_id, user_id = map(int, call.data.split("_")[1:])
            try:
                cursor.execute("UPDATE tournaments SET winner_id = %s WHERE id = %s", (user_id, tournament_id))
                cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = %s", (user_id,))
                conn.commit()
                bot.send_message(call.message.chat.id, "Победитель успешно установлен.")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Ошибка: {e}")



# Остальной функционал не изменяется

# Создание турнира
# Создание турнира
@bot.message_handler(func=lambda message: message.text == "Создать турнир")
def create_tournament_type(message):
    """Выбор типа турнира для создания."""
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для создания турниров.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Создать одиночный турнир", "Создать командный турнир")
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите тип турнира:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Создать одиночный турнир")
def create_single_tournament(message):
    """Инициализация создания одиночного турнира."""
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.")
        return
    user_states[message.chat.id] = {"state": "creating_single_tournament"}
    bot.send_message(message.chat.id, "Введите название одиночного турнира:")

@bot.message_handler(func=lambda message: message.text == "Создать командный турнир")
def create_team_tournament(message):
    """Инициализация создания командного турнира."""
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.")
        return
    user_states[message.chat.id] = {"state": "creating_team_tournament"}
    bot.send_message(message.chat.id, "Введите название командного турнира:")


@bot.message_handler(
    func=lambda message: user_states.get(message.chat.id, {}).get("state") == "creating_single_tournament")
def handle_tournament_name(message):
    """Обработка ввода названия турнира."""
    user_id = message.chat.id
    name = message.text.strip()

    # Сохраняем название турнира
    user_states[user_id]["name"] = name
    user_states[user_id]["state"] = "entering_tournament_time"  # Переход к следующему шагу
    bot.send_message(user_id,
                     "Введите время турнира в формате 'год_месяц_число час:минуты:секунды' (например, 2024_12_31 15:30:00).")


@bot.message_handler(
    func=lambda message: user_states.get(message.chat.id, {}).get("state") == "entering_tournament_time"
)
def handle_tournament_time(message):
    """Обработка ввода времени турнира."""
    user_id = message.chat.id
    state = user_states[user_id]
    name = state.get("name")
    time_input = message.text.strip()

    try:
        timezone = pytz.timezone('Asia/Novosibirsk')  # Укажите нужный часовой пояс
        now = datetime.now(timezone)

        tournament_time = datetime.strptime(time_input, "%Y_%m_%d %H:%M:%S")
        tournament_time = timezone.localize(tournament_time)  # Локализуем время турнира

        if tournament_time <= now:
            bot.send_message(user_id, "Ошибка! Время проведения турнира должно быть в будущем.")
            return

        # Сохранение турнира и получение ID
        cursor.execute(
            "INSERT INTO tournaments (game_name, time) VALUES (%s, %s) RETURNING id",
            (name, tournament_time)
        )
        tournament_id = cursor.fetchone()[0]
        conn.commit()

        # Добавление задач в планировщик
        scheduler.add_job(
            send_notification_to_participants,
            'date',
            run_date=tournament_time - timedelta(hours=1),
            args=[tournament_id, "1 час"],
            misfire_grace_time=3600  # 1 час на выполнение пропущенной задачи
        )
        scheduler.add_job(
            send_notification_to_participants,
            'date',
            run_date=tournament_time - timedelta(minutes=10),
            args=[tournament_id, "10 минут"],
            misfire_grace_time=600  # 10 минут на выполнение пропущенной задачи
        )

        bot.send_message(user_id, f"Турнир '{name}' успешно создан на {tournament_time}.", reply_markup=get_main_menu())
        user_states.pop(user_id)  # Очистка состояния
    except ValueError:
        bot.send_message(user_id, "Неверный формат времени. Используйте 'год_месяц_число час:минуты:секунды'.")
    except Exception as e:
        bot.send_message(user_id, f"Ошибка при создании турнира: {e}")



@bot.message_handler(
    func=lambda message: user_states.get(message.chat.id, {}).get("state") == "creating_team_tournament")
def handle_team_tournament_name(message):
    """Обработка ввода названия командного турнира."""
    user_id = message.chat.id
    name = message.text.strip()

    # Сохраняем название турнира
    user_states[user_id]["name"] = name
    user_states[user_id]["state"] = "entering_team_tournament_time"  # Переход к следующему шагу
    bot.send_message(user_id,
                     "Введите время командного турнира в формате 'год_месяц_число час:минуты:секунды' (например, 2024_12_31 15:30:00).")

def send_notification_to_team_tournament_participants(tournament_id, time_left):
    """Уведомление всех участников командного турнира."""
    try:
        # Получение информации о командном турнире
        cursor.execute("""
            SELECT game_name, time FROM team_tournaments WHERE id = %s
        """, (tournament_id,))
        tournament = cursor.fetchone()

        if not tournament:
            return  # Если турнир не найден, завершаем

        game_name, tournament_time = tournament

        # Получение участников турнира через команды
        cursor.execute("""
            SELECT DISTINCT tm.user_id
            FROM team_tournament_participants ttp
            INNER JOIN team_members tm ON ttp.team_id = tm.team_id
            WHERE ttp.tournament_id = %s
        """, (tournament_id,))
        participants = cursor.fetchall()

        # Отправка уведомлений всем участникам
        for participant in participants:
            try:
                bot.send_message(participant[0], f"Командный турнир '{game_name}' начнется через {time_left}.")
            except Exception as e:
                print(f"Ошибка при отправке уведомления пользователю {participant[0]}: {e}")
    except Exception as e:
        print(f"Ошибка при уведомлении участников командного турнира: {e}")


@bot.message_handler(
    func=lambda message: user_states.get(message.chat.id, {}).get("state") == "entering_team_tournament_time"
)
def handle_team_tournament_time(message):
    """Обработка ввода времени командного турнира."""
    user_id = message.chat.id
    state = user_states[user_id]
    name = state.get("name")
    time_input = message.text.strip()

    try:
        # Проверка формата времени
        timezone = pytz.timezone('Asia/Novosibirsk')  # Укажите ваш часовой пояс
        now = datetime.now(timezone)
        tournament_time = datetime.strptime(time_input, "%Y_%m_%d %H:%M:%S")
        tournament_time = timezone.localize(tournament_time)

        if tournament_time <= now:
            bot.send_message(user_id, "Ошибка! Время проведения турнира должно быть в будущем.")
            return

        # Сохранение турнира и получение ID
        cursor.execute(
            "INSERT INTO team_tournaments (game_name, time) VALUES (%s, %s) RETURNING id",
            (name, tournament_time)
        )
        tournament_id = cursor.fetchone()[0]
        conn.commit()

        # Добавление задач в планировщик
        scheduler.add_job(
            send_notification_to_team_tournament_participants,
            'date',
            run_date=tournament_time - timedelta(hours=1),
            args=[tournament_id, "1 час"],
            misfire_grace_time=3600  # 1 час на выполнение пропущенной задачи
        )
        scheduler.add_job(
            send_notification_to_team_tournament_participants,
            'date',
            run_date=tournament_time - timedelta(minutes=10),
            args=[tournament_id, "10 минут"],
            misfire_grace_time=600  # 10 минут на выполнение пропущенной задачи
        )

        bot.send_message(user_id, f"Командный турнир '{name}' успешно создан на {tournament_time}.",
                         reply_markup=get_main_menu())
        user_states.pop(user_id)  # Очистка состояния
    except ValueError:
        bot.send_message(user_id, "Неверный формат времени. Используйте 'год_месяц_число час:минуты:секунды'.")
    except Exception as e:
        conn.rollback()  # Откат транзакции в случае ошибки
        bot.send_message(user_id, f"Ошибка при создании командного турнира: {e}")
        user_states.pop(user_id)  # Очистка состояния в случае ошибки





# Отмена текущего действия
@bot.message_handler(commands=['cancel'])
def cancel_action(message):
    if message.chat.id in user_states:
        user_states.pop(message.chat.id)
        bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_main_menu())
    else:
        bot.send_message(message.chat.id, "Нечего отменять.", reply_markup=get_main_menu())
# Удаление турнира

@bot.message_handler(func=lambda message: message.text == "Удалить турнир")
def delete_tournament_type(message):
    """Выбор типа турниров для удаления."""
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для удаления турниров.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Удалить одиночный турнир", "Удалить командный турнир")
    markup.add("Назад")
    user_states[message.chat.id] = {"state": "choosing_tournament_type"}
    bot.send_message(message.chat.id, "Выберите тип турнира для удаления:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "Удалить одиночный турнир")
def delete_single_tournament(message):
    """Вывод списка одиночных турниров для выбора удаления."""
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.")
        return

    try:
        # Получение списка одиночных турниров
        cursor.execute("SELECT id, game_name, time FROM tournaments")
        tournaments = cursor.fetchall()

        if not tournaments:
            bot.send_message(message.chat.id, "Нет доступных одиночных турниров для удаления.", reply_markup=get_main_menu())
            return

        # Формирование кнопок для выбора турнира
        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name, time in tournaments:
            markup.add(
                types.InlineKeyboardButton(
                    f"{game_name} ({time})", callback_data=f"delete_single_{tournament_id}"
                )
            )

        markup.add(types.InlineKeyboardButton("Назад", callback_data="delete_back"))
        bot.send_message(message.chat.id, "Выберите турнир для удаления:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}", reply_markup=get_main_menu())


@bot.message_handler(func=lambda message: message.text == "Удалить командный турнир")
def delete_team_tournament(message):
    """Вывод списка командных турниров для выбора удаления."""
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.")
        return

    try:
        # Получение списка командных турниров
        cursor.execute("SELECT id, game_name, time FROM team_tournaments")
        tournaments = cursor.fetchall()

        if not tournaments:
            bot.send_message(message.chat.id, "Нет доступных командных турниров для удаления.", reply_markup=get_main_menu())
            return

        # Формирование кнопок для выбора турнира
        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name, time in tournaments:
            markup.add(
                types.InlineKeyboardButton(
                    f"{game_name} ({time})", callback_data=f"delete_team_{tournament_id}"
                )
            )

        markup.add(types.InlineKeyboardButton("Назад", callback_data="delete_back"))
        bot.send_message(message.chat.id, "Выберите турнир для удаления:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}", reply_markup=get_main_menu())


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_single_") or call.data.startswith("delete_team_"))
def confirm_tournament_deletion(call):
    """Запрос подтверждения удаления турнира."""
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    # Определяем тип турнира и ID
    data = call.data.split("_")
    tournament_type = data[1]  # single или team
    tournament_id = int(data[2])

    # Сохраняем данные в состояние
    user_states[call.message.chat.id] = {
        "state": "confirming_deletion",
        "tournament_type": tournament_type,
        "tournament_id": tournament_id,
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Да", callback_data="confirm_delete"),
        types.InlineKeyboardButton("Нет", callback_data="cancel_delete"),
    )
    bot.edit_message_text(
        f"Вы уверены, что хотите удалить {'одиночный' if tournament_type == 'single' else 'командный'} турнир с ID {tournament_id}?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data == "confirm_delete")
def delete_confirmed_tournament(call):
    """Удаление выбранного турнира после подтверждения."""
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    state = user_states.get(call.message.chat.id, {})
    tournament_type = state.get("tournament_type")
    tournament_id = state.get("tournament_id")

    if not tournament_type or not tournament_id:
        bot.edit_message_text("Произошла ошибка. Пожалуйста, повторите попытку.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        return

    try:
        if tournament_type == "single":
            cursor.execute("DELETE FROM tournaments WHERE id = %s", (tournament_id,))
        elif tournament_type == "team":
            cursor.execute("DELETE FROM team_tournaments WHERE id = %s", (tournament_id,))
        conn.commit()

        bot.edit_message_text(f"Турнир с ID {tournament_id} успешно удалён.", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception as e:
        conn.rollback()
        bot.edit_message_text(f"Ошибка при удалении турнира: {e}", chat_id=call.message.chat.id, message_id=call.message.message_id)
    finally:
        user_states.pop(call.message.chat.id, None)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
def cancel_tournament_deletion(call):
    """Отмена удаления турнира."""
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    bot.edit_message_text("Удаление турнира отменено.", chat_id=call.message.chat.id, message_id=call.message.message_id)
    user_states.pop(call.message.chat.id, None)


@bot.callback_query_handler(func=lambda call: call.data == "delete_back")
def handle_delete_back(call):
    """Обработка кнопки 'Назад' при выборе турнира для удаления."""
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    user_states.pop(call.message.chat.id, None)
    bot.edit_message_text("Вы вернулись назад.", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    delete_tournament_type(call.message)



@bot.message_handler(func=lambda message: message.text == "Назад")
def handle_back(message):
    """Обработка кнопки 'Назад'."""
    user_id = message.chat.id
    if user_states.get(user_id):
        user_states.pop(user_id)  # Очищаем состояние пользователя
    bot.send_message(user_id, "Вы вернулись в главное меню.", reply_markup=get_main_menu())


@bot.message_handler(func=lambda message: message.text == "Турниры")
def tournaments_menu(message):
    """Показывает меню выбора типа турниров."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Одиночные турниры", "Командные турниры")
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите тип турниров для просмотра:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "Одиночные турниры")
def list_single_tournaments(message):
    """Показывает список одиночных турниров."""
    try:
        safe_execute("SELECT game_name, time FROM tournaments WHERE winner_id IS NULL")
        tournaments = cursor.fetchall()
        if tournaments:
            response = "Список одиночных турниров:\n"
            for game, time in tournaments:
                response += f"- {game}: {time}\n"
        else:
            response = "Одиночные турниры отсутствуют."
        bot.send_message(message.chat.id, response, reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при получении списка одиночных турниров: {e}")


@bot.message_handler(func=lambda message: message.text == "Командные турниры")
def register_team_tournament(message):
    """Вывод списка командных турниров для регистрации."""
    try:
        cursor.execute("SELECT id, game_name, time FROM team_tournaments")
        tournaments = cursor.fetchall()
        if not tournaments:
            bot.send_message(message.chat.id, "На данный момент нет доступных командных турниров.", reply_markup=get_main_menu())
            return

        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name, time in tournaments:
            markup.add(
                types.InlineKeyboardButton(
                    f"{game_name} ({time})",
                    callback_data=f"register_team_{tournament_id}"
                )
            )
        bot.send_message(message.chat.id, "Выберите командный турнир для регистрации:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при получении списка командных турниров: {e}")

def send_notification_to_participants(tournament_id, time_left):
    try:
        # Получение информации о турнире
        cursor.execute("""
            SELECT game_name FROM tournaments WHERE id = %s
        """, (tournament_id,))
        tournament = cursor.fetchone()

        if not tournament:
            return  # Если турнир не найден, завершаем

        game_name = tournament[0]

        # Получение участников турнира
        cursor.execute("""
            SELECT u.user_id FROM tournament_participants tp
            INNER JOIN users u ON tp.user_id = u.user_id
            WHERE tp.tournament_id = %s
        """, (tournament_id,))
        participants = cursor.fetchall()

        # Отправка уведомлений всем участникам
        for participant in participants:
            user_id = participant[0]
            bot.send_message(user_id, f"Турнир '{game_name}' начнется через {time_left}.")
    except Exception as e:
        print(f"Ошибка при отправке уведомлений: {e}")

@bot.message_handler(func=lambda message: message.text == "Рассылка всем пользователям" and message.chat.id == ADMIN_ID)
def broadcast_to_all(message):
    """Инициализация рассылки всем пользователям."""
    bot.send_message(message.chat.id, "Введите сообщение для рассылки всем пользователям:")
    user_states[message.chat.id] = {"state": "broadcasting_to_all"}

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("state") == "broadcasting_to_all")
def handle_broadcast_to_all(message):
    """Обработка текста для рассылки всем пользователям."""
    admin_id = message.chat.id
    text = message.text

    try:
        # Получение списка всех пользователей
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()

        if not users:
            bot.send_message(admin_id, "Нет зарегистрированных пользователей для рассылки.")
            return

        # Отправка сообщения каждому пользователю
        for user in users:
            try:
                bot.send_message(user[0], text)
            except Exception as e:
                print(f"Ошибка при отправке пользователю {user[0]}: {e}")

        bot.send_message(admin_id, "Сообщение успешно отправлено всем пользователям.", reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(admin_id, f"Ошибка при рассылке: {e}", reply_markup=get_main_menu())
    finally:
        user_states.pop(admin_id, None)  # Очистка состояния

@bot.message_handler(func=lambda message: message.text == "Рассылка участникам турниров" and message.chat.id == ADMIN_ID)
def broadcast_to_tournaments(message):
    """Инициализация выбора типа турниров для рассылки."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Рассылка для одиночных турниров", "Рассылка для командных турниров")
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите тип турнира для рассылки:", reply_markup=markup)



@bot.message_handler(func=lambda message: message.text in ["Рассылка для одиночных турниров", "Рассылка для командных турниров"])
def choose_tournament_type(message):
    """Выбор турнира для рассылки по типу турнира."""
    if message.chat.id != ADMIN_ID:  # Проверка на права администратора
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этого действия.", reply_markup=get_main_menu())
        return

    tournament_type = "single" if message.text == "Рассылка для одиночных турниров" else "team"
    try:
        # Запрос турниров по типу
        if tournament_type == "single":
            cursor.execute("SELECT id, game_name, time FROM tournaments")
        else:
            cursor.execute("SELECT id, game_name, time FROM team_tournaments")
        tournaments = cursor.fetchall()

        if not tournaments:
            bot.send_message(message.chat.id, "Нет доступных турниров для рассылки.")
            return

        # Формирование клавиатуры с турнирами
        markup = types.InlineKeyboardMarkup()
        for tournament_id, game_name, time in tournaments:
            markup.add(
                types.InlineKeyboardButton(
                    f"{game_name} ({time})",
                    callback_data=f"broadcast_{tournament_type}_{tournament_id}"
                )
            )

        bot.send_message(message.chat.id, "Выберите турнир для рассылки:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при получении списка турниров: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("broadcast_"))
def handle_broadcast_tournament_selection(call):
    """Обработка выбора турнира для рассылки."""
    if call.message.chat.id != ADMIN_ID:  # Проверка на права администратора
        bot.answer_callback_query(call.id, "У вас нет прав для выполнения этого действия.")
        return

    data = call.data.split("_")
    tournament_type = data[1]
    tournament_id = int(data[2])

    # Сохраняем состояние для ввода сообщения
    user_states[call.message.chat.id] = {
        "state": "broadcasting_to_tournament",
        "tournament_id": tournament_id,
        "tournament_type": tournament_type
    }
    bot.send_message(call.message.chat.id, "Введите сообщение для участников выбранного турнира:")

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("state") == "broadcasting_to_tournament")
def handle_broadcast_to_tournament(message):
    """Обработка текста для рассылки участникам турнира."""
    admin_id = message.chat.id
    state = user_states[admin_id]
    tournament_id = state.get("tournament_id")
    tournament_type = state.get("tournament_type")
    text = message.text

    try:
        # Запрос участников турнира
        if tournament_type == "single":
            cursor.execute("""
                SELECT u.user_id 
                FROM tournament_participants tp
                INNER JOIN users u ON tp.user_id = u.user_id
                WHERE tp.tournament_id = %s
            """, (tournament_id,))
        else:
            cursor.execute("""
                SELECT DISTINCT tm.user_id 
                FROM team_tournament_participants ttp
                INNER JOIN team_members tm ON ttp.team_id = tm.team_id
                WHERE ttp.tournament_id = %s
            """, (tournament_id,))
        participants = cursor.fetchall()

        if not participants:
            bot.send_message(admin_id, "Нет участников в данном турнире для рассылки.")
            return

        # Отправка сообщения каждому участнику
        for participant in participants:
            try:
                bot.send_message(participant[0], text)
            except Exception as e:
                print(f"Ошибка при отправке пользователю {participant[0]}: {e}")

        bot.send_message(admin_id, "Сообщение успешно отправлено участникам турнира.", reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(admin_id, f"Ошибка при рассылке: {e}", reply_markup=get_main_menu())
    finally:
        user_states.pop(admin_id, None)  # Очистка состояния


#Мои турниры

@bot.message_handler(func=lambda message: message.text == "Мои турниры")
def my_tournaments(message):
    """Меню 'Мои турниры'."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Мои одиночные турниры", "Мои командные турниры")
    markup.add("Выйти из турнира")
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "Мои одиночные турниры")
def my_single_tournaments(message):
    """Показать все одиночные турниры пользователя."""
    user_id = message.chat.id
    try:
        # Получение списка одиночных турниров пользователя
        cursor.execute("""
            SELECT t.id, t.game_name, t.time 
            FROM tournament_participants tp
            INNER JOIN tournaments t ON tp.tournament_id = t.id
            WHERE tp.user_id = %s
        """, (user_id,))
        tournaments = cursor.fetchall()

        if not tournaments:
            bot.send_message(user_id, "Вы не участвуете ни в одном одиночном турнире.", reply_markup=get_main_menu())
            return

        # Формирование списка турниров
        response = "Ваши одиночные турниры:\n\n"
        for tournament_id, game_name, time in tournaments:
            response += f"ID: {tournament_id}, Название: {game_name}, Время: {time}\n"

        bot.send_message(user_id, response, reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(user_id, f"Ошибка при получении турниров: {e}", reply_markup=get_main_menu())


@bot.message_handler(func=lambda message: message.text == "Мои командные турниры")
def my_team_tournaments(message):
    """Показать все командные турниры пользователя."""
    user_id = message.chat.id
    try:
        # Получение списка командных турниров пользователя
        cursor.execute("""
            SELECT tt.id, tt.game_name, tt.time
            FROM team_tournament_participants ttp
            INNER JOIN team_members tm ON ttp.team_id = tm.team_id
            INNER JOIN team_tournaments tt ON ttp.tournament_id = tt.id
            WHERE tm.user_id = %s
        """, (user_id,))
        tournaments = cursor.fetchall()

        if not tournaments:
            bot.send_message(user_id, "Вы не участвуете ни в одном командном турнире.", reply_markup=get_main_menu())
            return

        # Формирование списка турниров
        response = "Ваши командные турниры:\n\n"
        for tournament_id, game_name, time in tournaments:
            response += f"ID: {tournament_id}, Название: {game_name}, Время: {time}\n"

        bot.send_message(user_id, response, reply_markup=get_main_menu())
    except Exception as e:
        bot.send_message(user_id, f"Ошибка при получении турниров: {e}", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "Выйти из турнира")
def leave_tournament(message):
    """Меню выхода из турниров."""
    user_id = message.chat.id
    try:
        # Получение всех турниров (одиночных и командных), где участвует пользователь
        cursor.execute("""
            SELECT 'single', t.id, t.game_name
            FROM tournament_participants tp
            INNER JOIN tournaments t ON tp.tournament_id = t.id
            WHERE tp.user_id = %s
            UNION
            SELECT 'team', tt.id, tt.game_name
            FROM team_tournament_participants ttp
            INNER JOIN team_members tm ON ttp.team_id = tm.team_id
            INNER JOIN team_tournaments tt ON ttp.tournament_id = tt.id
            WHERE tm.user_id = %s
        """, (user_id, user_id))
        tournaments = cursor.fetchall()

        if not tournaments:
            bot.send_message(user_id, "Вы не участвуете ни в одном турнире.", reply_markup=get_main_menu())
            return

        # Формирование кнопок для выбора турнира
        markup = types.InlineKeyboardMarkup()
        for t_type, t_id, game_name in tournaments:
            markup.add(types.InlineKeyboardButton(f"{game_name} ({'Одиночный' if t_type == 'single' else 'Командный'})",
                                                  callback_data=f"leave_{t_type}_{t_id}"))

        markup.add(types.InlineKeyboardButton("Назад", callback_data="leave_back"))
        bot.send_message(user_id, "Выберите турнир для выхода:", reply_markup=markup)
    except Exception as e:
        bot.send_message(user_id, f"Ошибка: {e}", reply_markup=get_main_menu())


@bot.callback_query_handler(func=lambda call: call.data.startswith("leave_"))
def confirm_leave_tournament(call):
    """Подтверждение выхода из турнира."""
    user_id = call.message.chat.id
    data = call.data.split("_")

    if len(data) < 3:  # Если данных для турнира недостаточно, вернуться в меню
        try:
            bot.answer_callback_query(call.id, "Невозможно обработать запрос. Пожалуйста, попробуйте снова.")
        except Exception as e:
            print(f"Ошибка при отправке ответа на callback: {e}")
        return

    t_type = data[1]  # single или team
    t_id = int(data[2])  # ID турнира

    # Проверка прав для командного турнира
    if t_type == "team":
        cursor.execute("""
            SELECT t.leader_id
            FROM teams t
            INNER JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.user_id = %s
        """, (user_id,))
        leader_id = cursor.fetchone()
        if not leader_id or leader_id[0] != user_id:
            try:
                bot.answer_callback_query(call.id, "Только лидер команды может выйти из командного турнира.")
            except Exception as e:
                print(f"Ошибка при отправке ответа на callback: {e}")
            return

    # Сохранение данных для подтверждения
    user_states[user_id] = {"state": "confirming_leave", "tournament_type": t_type, "tournament_id": t_id}

    # Ответ на callback-запрос сразу, чтобы избежать ошибки таймаута
    try:
        bot.answer_callback_query(call.id, "Выберите действие.")
    except Exception as e:
        print(f"Ошибка при отправке ответа на callback: {e}")

    # Кнопки для подтверждения
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Да", callback_data="confirm_leave"),
        types.InlineKeyboardButton("Нет", callback_data="cancel_leave"),
    )
    bot.edit_message_text("Вы уверены, что хотите выйти из турнира?", chat_id=user_id,
                          message_id=call.message.message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "confirm_leave")
def leave_tournament_confirmed(call):
    """Выход из турнира."""
    user_id = call.message.chat.id
    state = user_states.get(user_id, {})
    t_type = state.get("tournament_type")
    t_id = state.get("tournament_id")

    if not t_type or not t_id:
        bot.edit_message_text("Произошла ошибка. Попробуйте ещё раз.", chat_id=user_id, message_id=call.message.message_id)
        return

    try:
        if t_type == "single":
            cursor.execute("DELETE FROM tournament_participants WHERE tournament_id = %s AND user_id = %s", (t_id, user_id))
        elif t_type == "team":
            cursor.execute("""
                DELETE FROM team_tournament_participants 
                WHERE tournament_id = %s AND team_id = (
                    SELECT team_id FROM team_members WHERE user_id = %s
                )
            """, (t_id, user_id))
        conn.commit()
        bot.edit_message_text("Вы успешно вышли из турнира.", chat_id=user_id, message_id=call.message.message_id)
    except Exception as e:
        conn.rollback()
        bot.edit_message_text(f"Ошибка при выходе из турнира: {e}", chat_id=user_id, message_id=call.message.message_id)
    finally:
        user_states.pop(user_id, None)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_leave")
def cancel_leave_tournament(call):
    """Отмена выхода из турнира."""
    user_states.pop(call.message.chat.id, None)
    bot.edit_message_text("Выход из турнира отменён.", chat_id=call.message.chat.id, message_id=call.message.message_id)



# Обработка любых текстовых сообщений
@bot.message_handler(func=lambda message: True)
def default_handler(message):
    if message.chat.id in user_states:
        bot.send_message(message.chat.id, "Вы в процессе создания турнира. Введите данные или отмените действие (/cancel).")
    else:
        bot.send_message(message.chat.id, "Выберите действие из меню.", reply_markup=get_main_menu())

# Запуск бота
bot.polling(none_stop=True, interval=0)




