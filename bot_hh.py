import telebot
from telebot import types
import psycopg2
import requests
from psycopg2.extensions import register_adapter
from psycopg2.extras import Json
import os

# Подключение к базе данных
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

# Проверка и создание таблицы, если она не существует
cursor.execute("""
    CREATE TABLE IF NOT EXISTS vacancies (
        id SERIAL PRIMARY KEY,
        vacancy_title VARCHAR(255),
        company_name VARCHAR(255),
        salary_from NUMERIC,
        experience VARCHAR(255),
        format VARCHAR(255),
        description TEXT,
        salary_currency VARCHAR(10),
        salary_to NUMERIC
    )
""")
conn.commit()

# Токен бота
token = "6127897344:AAFqWTiZ7YdIgtL0uKcQwQszRki-g8m9GvA"

bot = telebot.TeleBot(token)

# Состояния пользователя
STATE_WAIT_COMMAND = 0
STATE_WAIT_SALARY = 1
STATE_WAIT_PROFESSION = 2
STATE_WAIT_EXPERIENCE = 3
STATE_WAIT_FORMAT = 4

# Словарь для хранения состояний пользователей
user_states = {}

# Парсинг данных о вакансиях
def parse_hh_vacancies(profession_name):
    response = requests.get(f'https://api.hh.ru/vacancies?text={profession_name}')
    data = response.json()
    register_adapter(dict, Json)

    for vacancy in data['items']:
        employer_dict = vacancy.get('employer', {})
        salary_dict = vacancy.get('salary', {})
        experience_dict = vacancy.get('experience', {})
        employment_dict = vacancy.get('employment', {})
        snippet_dict = vacancy.get('snippet', {})

        if not salary_dict:
            salary_dict = {'from': None, 'to': None, 'currency': None}

        cursor.execute("""
            INSERT INTO vacancies (vacancy_title, company_name, salary_from, experience, format, description, salary_currency, salary_to) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            vacancy['name'],  # Название вакансии
            employer_dict.get('name', 'N/A'),  # Компания
            salary_dict.get('from'),  # Зарплата (нижняя граница)
            experience_dict.get('name', 'N/A'),  # Опыт
            employment_dict.get('name', 'N/A'),  # Формат работы
            snippet_dict.get('responsibility', 'N/A'),  # Описание
            salary_dict.get('currency', 'N/A'),  # Зарплата (валюта)
            salary_dict.get('to')  # Зарплата (верхняя граница)
        ))

    conn.commit()

# Отправка сообщений о вакансиях
def send_vacancy_messages(vacancy_title, user_id):
    cursor.execute("SELECT * FROM vacancies WHERE vacancy_title LIKE %s", (f"%{vacancy_title}%",))
    vacancies = cursor.fetchall()

    if not vacancies:
        bot.send_message(user_id, text="Вакансий с таким названием не найдено!")
    else:
        for vacancy in vacancies:
            vacancy_title = vacancy[1]
            company_name = vacancy[2]
            salary_from = vacancy[3]
            experience = vacancy[4]
            format = vacancy[5]
            description = vacancy[6]
            salary_currency = vacancy[7]
            salary_to = vacancy[8]

            message = f"Вакансия: {vacancy_title}\n"
            message += f"Компания: {company_name}\n"
            message += f"Зарплата: {salary_from}-{salary_to} {salary_currency}\n"
            message += f"Опыт: {experience}\n"
            message += f"Формат: {format}\n"
            message += f"Описание: {description}\n"

            bot.send_message(user_id, text=message)

    user_states[user_id] = STATE_WAIT_COMMAND

# Старт
@bot.message_handler(commands=['start'])
def start(message):
    keyboard = types.ReplyKeyboardMarkup()
    keyboard.row("/help", "/hh")
    keyboard.row("/name_of_profession", "/salary_from")
    keyboard.row("/format", "/experience")
    bot.send_message(message.chat.id, 'Привет! Хочешь посмотреть самые свежие вакансии с hh.ru? Тогда давай начнём! :)', reply_markup=keyboard)

# ЧТО УМЕЕТ БОТ
@bot.message_handler(commands=['help'])
def start_message(message):
    bot.send_message(message.chat.id, 'Я могу: \nОтправить ссылку на hh.ru по команде "/hh"; \nНайти вакансии по указанной должности по команде "/name_of_profession"; \nСделать выборку вакансий по зарплате по команде "/salary_from"; \nСделать выборку вакансий по формату работы по команде "/format"; \nСделать выборку вакансий по опыту работы по команде "/experience"; \nПомочь по команде "/help"\n')

# САЙТ HH.RU
@bot.message_handler(commands=['hh'])
def start_message(message):
    bot.send_message(message.chat.id, 'https://hh.ru/')

# ДОЛЖНОСТЬ
@bot.message_handler(commands=['name_of_profession'])
def handle_message(message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_WAIT_PROFESSION
    bot.send_message(message.chat.id, "Отлично! Введите должность, вакансии на которую вы хотите найти!")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == STATE_WAIT_PROFESSION)
def handle_message(message):
    profession_name = message.text.lower()
    user_id = message.from_user.id
    bot.send_message(message.chat.id, f"Отлично! Все вакансии с названием {profession_name} скоро будут отправлены!")
    parse_hh_vacancies(profession_name)
    bot.send_message(message.chat.id, "Вакансии загружены!")
    send_vacancy_messages(profession_name, user_id)

# ЗАРПЛАТА
@bot.message_handler(commands=['salary_from'])
def handle_salary_command(message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_WAIT_SALARY
    bot.send_message(chat_id=message.chat.id, text="Введите желаемую зарплату:")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == STATE_WAIT_SALARY)
def handle_salary_input(message):
    user_id = message.from_user.id

    try:
        salary = (int(message.text),)
        cursor.execute("SELECT * FROM vacancies WHERE salary_from >= %s", salary)
        vacancies = cursor.fetchall()

        if vacancies:
            for vacancy in vacancies:
                vacancy_title = vacancy[1]
                company_name = vacancy[2]
                salary_from = vacancy[3]
                experience = vacancy[4]
                format = vacancy[5]
                description = vacancy[6]
                salary_currency = vacancy[7]
                salary_to = vacancy[8]

                message = f"Вакансия: {vacancy_title}\n"
                message += f"Компания: {company_name}\n"
                message += f"Зарплата: {salary_from}-{salary_to} {salary_currency}\n"
                message += f"Опыт: {experience}\n"
                message += f"Формат: {format}\n"
                message += f"Описание: {description}\n"

                bot.send_message(user_id, text=message)
        else:
            bot.send_message(chat_id=message.chat.id, text="Вакансий с такой зарплатой не найдено.")

        user_states[user_id] = STATE_WAIT_COMMAND

    except ValueError:
        bot.send_message(chat_id=message.chat.id, text="Ошибка! Введите число!")

# ФОРМАТ
@bot.message_handler(commands=['format'])
def handle_format_command(message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_WAIT_FORMAT
    bot.send_message(chat_id=message.chat.id, text="Введите нужный формат работы по шаблону: \n- Полная занятость \n- Частичная занятость \n- Проектная работа/разовое задание \n- Волонтерство \n- Стажировка")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == STATE_WAIT_FORMAT)
def handle_format_input(message):
    user_id = message.from_user.id

    format = message.text
    cursor.execute("SELECT * FROM vacancies WHERE format LIKE %s", (f"%{format}%",))
    vacancies = cursor.fetchall()

    if vacancies:
        for vacancy in vacancies:
            vacancy_title = vacancy[1]
            company_name = vacancy[2]
            salary_from = vacancy[3]
            experience = vacancy[4]
            format = vacancy[5]
            description = vacancy[6]
            salary_currency = vacancy[7]
            salary_to = vacancy[8]

            message = f"Вакансия: {vacancy_title}\n"
            message += f"Компания: {company_name}\n"
            message += f"Зарплата: {salary_from}-{salary_to} {salary_currency}\n"
            message += f"Опыт: {experience}\n"
            message += f"Формат: {format}\n"
            message += f"Описание: {description}\n"

            bot.send_message(user_id, text=message)
    else:
        bot.send_message(chat_id=message.chat.id, text="Вакансий такого формата работы не найдено. Проверьте корректность введенных данных!")

    user_states[user_id] = STATE_WAIT_COMMAND

# ОПЫТ
@bot.message_handler(commands=['experience'])
def handle_experience_command(message):
    user_id = message.from_user.id
    user_states[user_id] = STATE_WAIT_EXPERIENCE
    bot.send_message(chat_id=message.chat.id, text="Введите ваш опыт работы в одном из форматов: \n- Нет опыта \n- От 1 года до 3 лет \n- От 3 до 6 лет \n- Более 6 лет")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == STATE_WAIT_EXPERIENCE)
def handle_experience_input(message):
    user_id = message.from_user.id

    experience = message.text
    cursor.execute("SELECT * FROM vacancies WHERE experience LIKE %s", (f"%{experience}%",))
    vacancies = cursor.fetchall()

    if vacancies:
        for vacancy in vacancies:
            vacancy_title = vacancy[1]
            company_name = vacancy[2]
            salary_from = vacancy[3]
            experience = vacancy[4]
            format = vacancy[5]
            description = vacancy[6]
            salary_currency = vacancy[7]
            salary_to = vacancy[8]

            message = f"Вакансия: {vacancy_title}\n"
            message += f"Компания: {company_name}\n"
            message += f"Зарплата: {salary_from}-{salary_to} {salary_currency}\n"
            message += f"Опыт: {experience}\n"
            message += f"Формат: {format}\n"
            message += f"Описание: {description}\n"

            bot.send_message(user_id, text=message)
    else:
        bot.send_message(chat_id=message.chat.id, text="Вакансий с таким опытом не найдено. Проверьте корректность введенных данных!")

    user_states[user_id] = STATE_WAIT_COMMAND

# ОБРАБОТКА СООБЩЕНИЙ ВНЕ КОНТЕКСТА
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) != STATE_WAIT_PROFESSION and user_states.get(message.from_user.id) != STATE_WAIT_SALARY and user_states.get(message.from_user.id) != STATE_WAIT_FORMAT and user_states.get(message.from_user.id) != STATE_WAIT_EXPERIENCE)
def handle_default(message):
    bot.send_message(chat_id=message.chat.id, text="Извините, я вас не понимаю!")

bot.infinity_polling()
