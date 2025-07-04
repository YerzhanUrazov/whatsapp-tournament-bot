import os
import requests
from flask import Flask, request

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

app = Flask(__name__)

@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    chat_id = data["message"]["chat"]["id"]
    message_text = data["message"].get("text", "")

    if message_text == "/start":
        send_message(chat_id, "Привет! Бот работает ✅")

    return "", 200

def send_message(chat_id, text):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

if __name__ == "__main__":
    print("🚀 Бот запущен без telegram.ext")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
