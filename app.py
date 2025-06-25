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

ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
PHONE_NUMBER_ID = "733866206470935"
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
            writer.writerow(["Номер", "Имя", "Фамилия", "Турнир", "Дата", "Время"])
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

def convert_to_wa_id(phone):
    if phone.startswith("770"):
        return "78" + phone[1:]
    return phone

def send_message(to_number, message_text):
    to_number = to_number.replace("+", "").replace(" ", "")
    to_number = convert_to_wa_id(to_number)

    logging.info(f"📞 Отправка на номер: {to_number}")

    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": message_text
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        logging.error(f"❌ Ошибка отправки: {response.status_code}, {response.text}")
    else:
        logging.info(f"📤 Отправлено сообщение: {message_text}")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode and token and mode == "subscribe" and token == "myverifytoken":
            logging.info("✅ Вебхук подтверждён!")
            return challenge, 200
        else:
            return "Ошибка подтверждения", 403

    elif request.method == "POST":
        data = request.get_json()

        if data and "entry" in data:
            for entry in data["entry"]:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    if messages:
                        message = messages[0]
                        text = message["text"]["body"].strip()
                        sender = message["from"]

                        logging.info(f"📩 Сообщение от {sender}: {text}")

                        state = user_states.get(sender, 'start')

                        if state == 'start':
                            description = get_tournament_description()
                            greeting = f"Приглашаем Вас принять участие в следующем турнире:\n{description}\n\nДля участия введите своё имя:"
                            send_message(sender, greeting)
                            user_states[sender] = 'wait_name'

                        elif state == 'wait_name':
                            user_data[sender] = {'name': text}
                            send_message(sender, "Спасибо! Теперь введи фамилию.")
                            user_states[sender] = 'wait_surname'

                        elif state == 'wait_surname':
                            user_data[sender]['surname'] = text
                            tournament = get_current_tournament()
                            send_message(sender, f"Вы уверены, что хотите зарегистрироваться на турнир '{tournament}'? Ответьте 1 — Да, 2 — Нет.")
                            user_states[sender] = 'confirm'

                        elif state == 'confirm':
                            if text.strip() == '1':
                                send_message(sender, "✅ Ваша заявка принята! Спасибо!")
                                user_data_confirmed[sender] = user_data[sender].copy()
                                save_confirmed_user_to_file(sender, user_data[sender])
                                logging.info(f"📦 Данные участника: {user_data[sender]}")
                            else:
                                send_message(sender, "❌ Операция отменена.")
                            user_states.pop(sender, None)
                            user_data.pop(sender, None)

        return "OK", 200

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
