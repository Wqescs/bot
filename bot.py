import os, json
from datetime import date
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ConversationHandler,
    MessageHandler, ContextTypes, filters
)
from docxtpl import DocxTemplate
from docx2pdf import convert

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Состояния разговора
CHOOSING, SURNAME, NAME, PATRONYMIC = range(4)

# Загрузка данных
BASE_DIR = os.getcwd()
with open("data/allowed_users.json", encoding="utf-8") as f:
    ALLOWED = set(json.load(f))
with open("data/surnames.json", encoding="utf-8") as f:
    SURNAMES = set(json.load(f))
with open("data/names.json", encoding="utf-8") as f:
    NAMES = set(json.load(f))
with open("data/patronymics.json", encoding="utf-8") as f:
    PATRONYMICS = set(json.load(f))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username
    if user not in ALLOWED:
        await update.message.reply_text("Извини, этот бот не для тебя.")
        return ConversationHandler.END

    # Кнопки с файлами
    files = [f for f in os.listdir("templates") if f.endswith(".docx")]
    keyboard = ReplyKeyboardMarkup([[fn] for fn in files], one_time_keyboard=True)
    await update.message.reply_text("Выбери шаблон:", reply_markup=keyboard)
    return CHOOSING

async def choose_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["template"] = update.message.text
    await update.message.reply_text("Введите фамилию:")
    return SURNAME

async def ask_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in SURNAMES:
        await update.message.reply_text("Неверно — такой фамилии нет. Попробуй ещё:")
        return SURNAME
    context.user_data["surname"] = text
    await update.message.reply_text("Введите имя:")
    return NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in NAMES:
        await update.message.reply_text("Неверно — такого имени нет. Попробуй ещё:")
        return NAME
    context.user_data["name"] = text
    await update.message.reply_text("Введите отчество (или напиши «нет»):")
    return PATRONYMIC

async def ask_patronymic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "нет" and text not in PATRONYMICS:
        await update.message.reply_text("Нет такого отчества. Или напиши «нет»:")
        return PATRONYMIC
    context.user_data["patronymic"] = "" if text.lower()=="нет" else text

    # Рендерим и отправляем
    tpl_path = os.path.join("templates", context.user_data["template"])
    doc = DocxTemplate(tpl_path)
    ctx = {
        "surname": context.user_data["surname"],
        "name": context.user_data["name"],
        "patronymic": context.user_data["patronymic"],
        "date": date.today().strftime("%d.%m.%Y")
    }
    out_docx = f"out_{update.effective_user.id}.docx"
    out_pdf  = out_docx.replace(".docx", ".pdf")
    doc.render(ctx); doc.save(out_docx)
    convert(out_docx, out_pdf)

    # Отправка и уборка
    await update.message.reply_document(open(out_pdf, "rb"))
    os.remove(out_docx); os.remove(out_pdf)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отмена. Всего доброго!")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_template)],
            SURNAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_surname)],
            NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            PATRONYMIC:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_patronymic)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
