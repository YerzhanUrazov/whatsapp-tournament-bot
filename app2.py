import os
import requests
from flask import Flask, send_file, request
import logging
import csv
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import re

# ✅ Загрузка переменных окружения
if os.environ.get("FLASK_ENV") != "production":
    load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

user_data_confirmed = {}
user_states = {}  # состояние пользователя в чате
CONFIRMED_USERS_FILE = "confirmed_users.csv"

# 🔽 Настройка Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google-credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Турнир заявки").sheet1
config_sheet = client.open("Турнир заявки").worksheet("config")

def get_current_tournament():
    try:
        return config_sheet.acell("B1").value.strip()
    except Exception as e:
        logging.error(f"❌ Ошибка чтения турнира из Sheets: {e}")
        return ""

def get_tournament_description():
    try:
        return config_sheet.acell("B2").value.strip()
    except Exception as e:
        logging.error(f"❌ Ошибка чтения описания турнира из Sheets: {e}")
        return ""

def save_confirmed_user_to_file(user_id, data):
    is_new_file = not os.path.exists(CONFIRMED_USERS_FILE)
    timestamp = datetime.utcnow() + timedelta(hours=5)
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H:%M:%S")

    with open(CONFIRMED_USERS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["Номер", "Имя", "Фамилия", "Турнир", "Дата", "Время"])
        writer.writerow([
            data.get("phone", ""),
            data.get("name", ""),
            data.get("surname", ""),
            get_current_tournament(),
            date_str,
            time_str
        ])

    try:
        sheet.append_row([
            data.get("phone", ""),
            data.get("name", ""),
            data.get("surname", ""),
            get_current_tournament(),
            date_str,
            time_str
        ])
        logging.info("📄 Добавлено в Google Sheets")
    except Exception as e:
        logging.error(f"❌ Ошибка записи в Google Sheets: {e}")

@app.route("/export", methods=["GET"])
def export_users():
    if not os.path.exists(CONFIRMED_USERS_FILE):
        return "Нет данных для выгрузки", 200

    return send_file(
        CONFIRMED_USERS_FILE,
        mimetype="text/csv",
        as_attachment=True,
        download_name="users.csv"
    )

@app.route("/ping")
def ping():
    return "", 204

@app.route(f"/webhook/{os.environ['TELEGRAM_BOT_TOKEN']}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    message = data.get("message")
    if not message:
        return "", 204

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    user_state = user_states.get(chat_id, "start")
    user_data = user_data_confirmed.setdefault(chat_id, {})

    if text == "/start":
        description = get_tournament_description()
        greeting = f"Приглашаем Вас принять участие в следующем турнире:\n{description}\n\nДля участия введите свой номер телефона:"
        user_states[chat_id] = "wait_phone"
        reply = greeting

    elif user_state == "wait_phone":
        cleaned = re.sub(r"[\s\-\(\)]", "", text)
        if re.fullmatch(r"(\+7\d{10}|87\d{9})", cleaned):
            user_data["phone"] = text
            user_states[chat_id] = "wait_name"
            reply = "Теперь введите имя:"
        else:
            reply = "⚠️ Пожалуйста, введите корректный номер телефона в формате +7XXXXXXXXXX или 87XXXXXXXXX"

    elif user_state == "wait_name":
        user_data["name"] = text
        user_states[chat_id] = "wait_surname"
        reply = "Отлично! Теперь введите фамилию:"

    elif user_state == "wait_surname":
        user_data["surname"] = text
        user_states[chat_id] = "confirm"
        reply = f"Подтвердите регистрацию на турнир '{get_current_tournament()}'. Ответьте 1 — Да, 2 — Нет."

    elif user_state == "confirm":
        if text.strip() == "1":
            save_confirmed_user_to_file(chat_id, user_data)
            reply = "✅ Ваша заявка принята! Спасибо!"
        else:
            reply = "❌ Регистрация отменена."
        user_states[chat_id] = "done"

    else:
        reply = "Пожалуйста, начните с команды /start"

    token = os.environ['TELEGRAM_BOT_TOKEN']
    send_url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(send_url, json={
        "chat_id": chat_id,
        "text": reply
    })

    return "", 204

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
