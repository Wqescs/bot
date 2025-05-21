import inspect

if not hasattr(inspect, "getargspec"):
    def getargspec(func):
        """
        Возвращает кортеж (args, varargs, varkw, defaults),
        совместимый со старым inspect.getargspec.
        """
        spec = inspect.getfullargspec(func)
        return spec.args, spec.varargs, spec.varkw, spec.defaults
    inspect.getargspec = getargspec

import os
import json
from datetime import date

from dotenv import load_dotenv
import pymorphy2

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from docxtpl import DocxTemplate
from docx2pdf import convert

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

CHOOSING, SURNAME, NAME, PATRONYMIC = range(4)

with open("data/allowed_users.json",   encoding="utf-8") as f:
    ALLOWED      = set(json.load(f))
with open("data/surnames.json",         encoding="utf-8") as f:
    SURNAMES     = set(json.load(f))
with open("data/names.json",            encoding="utf-8") as f:
    NAMES        = set(json.load(f))
with open("data/patronymics.json",      encoding="utf-8") as f:
    PATRONYMICS  = set(json.load(f))

morph = pymorphy2.MorphAnalyzer()

def to_dative(word: str) -> str:
    """
    Склоняет слово в дательный падеж, предпочитая разборы
    с тэгами Surn, Name или Patr (фамилия, имя, отчество).
    Всегда возвращает с заглавной буквы.
    """
    parses = morph.parse(word)
    if not parses:
        return word.capitalize()

    for p in parses:
        tags = set(p.tag.grammemes)
        if {"Surn", "Name", "Patr"} & tags:
            inf = p.inflect({"datv"})
            if inf:
                return inf.word.capitalize()

    p = parses[0]
    inf = p.inflect({"datv"})
    if inf:
        return inf.word.capitalize()

    return word.capitalize()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username
    if user not in ALLOWED:
        await update.message.reply_text("Вы не являетесь пользователем бота.")
        return ConversationHandler.END

    files = [f for f in os.listdir("templates") if f.endswith(".docx")]
    keyboard = ReplyKeyboardMarkup([[fn] for fn in files], one_time_keyboard=True)
    await update.message.reply_text("Выберите шаблон:", reply_markup=keyboard)
    return CHOOSING

async def choose_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["template"] = update.message.text
    await update.message.reply_text("Введите фамилию:")
    return SURNAME

async def ask_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in SURNAMES:
        await update.message.reply_text("Фамилия введена неверно, либо отсутствует в базе. Попробуйте ещё:")
        return SURNAME

    context.user_data["surname"] = text
    await update.message.reply_text("Введите имя:")
    return NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in NAMES:
        await update.message.reply_text("Имя введено неверно, либо отсутствует в базе. Попробуйте ещё:")
        return NAME

    context.user_data["name"] = text
    await update.message.reply_text("Введите отчество (или напиши «нет»):")
    return PATRONYMIC

async def ask_patronymic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != "нет" and text not in PATRONYMICS:
        await update.message.reply_text("Отчество введено неверно, либо отсутствует в базе. Или напиши «нет»:")
        return PATRONYMIC

    # сохраняем отчество (или пусто)
    context.user_data["patronymic"] = "" if text.lower() == "нет" else text

    # уведомляем и убираем клавиатуру
    await update.message.reply_text(
        "Ожидайте. Формирую документ…",
        reply_markup=ReplyKeyboardRemove()
    )

    # готовим шаблон
    tpl_path = os.path.join("templates", context.user_data["template"])
    doc = DocxTemplate(tpl_path)

    # raw ФИО
    raw_surname = context.user_data["surname"]
    raw_name    = context.user_data["name"]
    raw_patr    = context.user_data["patronymic"]

    # склоняем в дательный падеж
    surname_datv = to_dative(raw_surname)
    name_datv    = to_dative(raw_name)
    patr_datv    = to_dative(raw_patr) if raw_patr else ""

    # контекст для шаблона
    ctx = {
        "surname_datv":     surname_datv,
        "name_datv":        name_datv,
        "patronymic_datv":  patr_datv,
        "date":             date.today().strftime("%d.%m.%Y")
    }

    # генерим и конвертим
    out_docx = f"out_{update.effective_user.id}.docx"
    out_pdf  = out_docx.replace(".docx", ".pdf")

    doc.render(ctx)
    doc.save(out_docx)
    convert(out_docx, out_pdf)

    # отправляем и чистим
    with open(out_pdf, "rb") as pdf_f:
        await update.message.reply_document(pdf_f)
    os.remove(out_docx)
    os.remove(out_pdf)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отмена. Всего доброго!")
    return ConversationHandler.END

# ─── Запуск ────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING:   [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_template)],
            SURNAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_surname)],
            NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            PATRONYMIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_patronymic)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
