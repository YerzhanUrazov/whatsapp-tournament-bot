import os
from flask import Flask, request, send_file
import requests
import logging
import csv
from io import StringIO, BytesIO
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# ✅ Загрузка переменных окружения, если не продакшн
if os.environ.get("FLASK_ENV") != "production":
    load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

user_states = {}  # user_id -> current step
user_data = {}    # user_id -> {name, surname, tournament}
user_data_confirmed = {}  # ✅ сюда сохраняем подтверждённых участников

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
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

def save_confirmed_user_to_file(number, data):
    is_new_file = not os.path.exists(CONFIRMED_USERS_FILE)
    timestamp = datetime.utcnow() + timedelta(hours=5)
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H:%M:%S")
    with open(CONFIRMED_USERS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["ID", "Имя", "Фамилия", "Турнир", "Дата", "Время"])
        writer.writerow([
            number,
            data.get("name", ""),
            data.get("surname", ""),
            get_current_tournament(),
            date_str,
            time_str
        ])

    try:
        sheet.append_row([
            number,
            data.get("name", ""),
            data.get("surname", ""),
            get_current_tournament(),
            date_str,
            time_str
        ])
        logging.info("📄 Добавлено в Google Sheets")
    except Exception as e:
        logging.error(f"❌ Ошибка записи в Google Sheets: {e}")

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def receive_update():
    data = request.get_json()
    logging.info(f"➡ Получено: {data}")
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").strip()

        state = user_states.get(chat_id, 'start')

        if state == 'start':
            description = get_tournament_description()
            greeting = f"Приглашаем Вас принять участие в следующем турнире:\n{description}\n\nДля участия введите своё имя:"
            send_telegram_message(chat_id, greeting)
            user_states[chat_id] = 'wait_name'

        elif state == 'wait_name':
            user_data[chat_id] = {'name': text}
            send_telegram_message(chat_id, "Спасибо! Теперь введи фамилию.")
            user_states[chat_id] = 'wait_surname'

        elif state == 'wait_surname':
            user_data[chat_id]['surname'] = text
            tournament = get_current_tournament()
            send_telegram_message(chat_id, f"Вы уверены, что хотите зарегистрироваться на турнир '{tournament}'? Ответьте 1 — Да, 2 — Нет.")
            user_states[chat_id] = 'confirm'

        elif state == 'confirm':
            if text == '1':
                send_telegram_message(chat_id, "✅ Ваша заявка принята! Спасибо!")
                user_data_confirmed[chat_id] = user_data[chat_id].copy()
                save_confirmed_user_to_file(chat_id, user_data[chat_id])
                logging.info(f"📦 Данные участника: {user_data[chat_id]}")
            else:
                send_telegram_message(chat_id, "❌ Операция отменена.")
            user_states.pop(chat_id, None)
            user_data.pop(chat_id, None)
    return {"ok": True}

def send_telegram_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

def set_webhook():
    webhook_url = f"https://whatsapp-tournament-bot.onrender.com/webhook/{BOT_TOKEN}"
    r = requests.get(f"{URL}/setWebhook?url={webhook_url}")
    print("Webhook setup:", r.text)

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

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
