from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

user_states = {}  # user_id -> current step
user_data = {}    # user_id -> {name, surname, tournament}

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = "733866206470935"

def convert_to_wa_id(phone):
    if phone.startswith("770"):
        return "78" + phone[1:]
    return phone


def send_message(to_number, message_text):
    to_number = to_number.replace("+", "").replace(" ", "")
    to_number = convert_to_wa_id(to_number)

    print(f"📞 Отправка на номер: {to_number}")  # 👉 добавлен вывод

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
        print(f"❌ Ошибка отправки: {response.status_code}, {response.text}")
    else:
        print(f"📤 Отправлено сообщение: {message_text}")


@app.route("/webhook", methods=["POST"])
def webhook():
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

                    print(f"Сообщение от {sender}: {text}")

                    state = user_states.get(sender, 'start')

                    if state == 'start':
                        send_message(sender, "Привет! Пожалуйста, введи своё имя.")
                        user_states[sender] = 'wait_name'

                    elif state == 'wait_name':
                        user_data[sender] = {'name': text}
                        send_message(sender, "Спасибо! Теперь введи фамилию.")
                        user_states[sender] = 'wait_surname'

                    elif state == 'wait_surname':
                        user_data[sender]['surname'] = text
                        send_message(sender, "Отлично! Выбери турнир:\n1. Летний\n2. Осенний\n3. Зимний")
                        user_states[sender] = 'wait_tournament'

                    elif state == 'wait_tournament':
                        user_data[sender]['tournament'] = text
                        name = user_data[sender]['name']
                        surname = user_data[sender]['surname']
                        tournament = user_data[sender]['tournament']
                        send_message(sender, f"Вы уверены, что хотите зарегистрироваться на турнир '{tournament}'? (да/нет)")
                        user_states[sender] = 'confirm'

                    elif state == 'confirm':
                        if text.lower() == 'да':
                            send_message(sender, "✅ Ваша заявка принята! Спасибо!")
                            print(f"📦 Данные участника: {user_data[sender]}")
                        else:
                            send_message(sender, "Операция отменена.")
                        user_states.pop(sender, None)
                        user_data.pop(sender, None)

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
