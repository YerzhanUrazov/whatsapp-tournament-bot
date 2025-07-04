import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio

# Загрузка токена
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Создаем Flask-приложение
app = Flask(__name__)

# Простой хендлер для команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Бот работает ✅")

# Обработка вебхука
@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    update = Update.de_json(data, application.bot)
    asyncio.create_task(application.process_update(update))
    return "", 204

# Установка вебхука
async def init_webhook():
    global application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    print("✅ Новый код загружен! (init_webhook)")
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(url=f"{os.environ['RENDER_EXTERNAL_URL']}/webhook/{TELEGRAM_TOKEN}")
    print("🚀 Вебхук установлен!")

# Запуск
if __name__ == "__main__":
    asyncio.run(init_webhook())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
