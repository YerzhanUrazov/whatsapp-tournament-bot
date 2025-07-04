import os
from flask import Flask, send_file
import logging
import csv
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler

# ✅ Загрузка переменных окружения
if os.environ.get("FLASK_ENV") != "production":
    load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

user_data_confirmed = {}  # ✅ сюда сохраняем подтверждённых участников
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

# Telegram bot logic
WAIT_PHONE, WAIT_NAME, WAIT_SURNAME, CONFIRM = range(4)

def start(update: Update, context: CallbackContext):
    button = KeyboardButton("📱 Отправить номер", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[button]], one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text(
        "Привет! Для регистрации, пожалуйста, отправьте свой номер телефона:",
        reply_markup=reply_markup
    )
    return WAIT_PHONE

def receive_phone(update: Update, context: CallbackContext):
    contact = update.message.contact
    if contact and contact.phone_number:
        phone = contact.phone_number
        context.user_data["phone"] = phone
        update.message.reply_text("Спасибо! Введите своё имя:")
        return WAIT_NAME
    else:
        update.message.reply_text("Пожалуйста, нажмите кнопку и отправьте номер.")
        return WAIT_PHONE

def wait_name(update: Update, context: CallbackContext):
    context.user_data["name"] = update.message.text
    update.message.reply_text("Отлично! Теперь введите свою фамилию:")
    return WAIT_SURNAME

def wait_surname(update: Update, context: CallbackContext):
    context.user_data["surname"] = update.message.text
    tournament = get_current_tournament()
    update.message.reply_text(f"Вы уверены, что хотите зарегистрироваться на турнир '{tournament}'? Ответьте 1 — Да, 2 — Нет.")
    return CONFIRM

def confirm(update: Update, context: CallbackContext):
    if update.message.text.strip() == '1':
        save_confirmed_user_to_file(update.effective_user.id, context.user_data)
        update.message.reply_text("✅ Ваша заявка принята! Спасибо!")
    else:
        update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("❌ Регистрация отменена.")
    return ConversationHandler.END

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

def main():
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_PHONE: [MessageHandler(Filters.contact, receive_phone)],
            WAIT_NAME: [MessageHandler(Filters.text & ~Filters.command, wait_name)],
            WAIT_SURNAME: [MessageHandler(Filters.text & ~Filters.command, wait_surname)],
            CONFIRM: [MessageHandler(Filters.text & ~Filters.command, confirm)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    dp.add_handler(conv_handler)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
