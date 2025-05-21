import inspect

if not hasattr(inspect, "getargspec"):
    def getargspec(func):
        spec = inspect.getfullargspec(func)
        return spec.args, spec.varargs, spec.varkw, spec.defaults
    inspect.getargspec = getargspec
import uuid

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

PERSISTENT_BUTTONS = ["Главное меню", "Отмена"]

def build_keyboard(rows: list[list[str]]):
    kb = rows + [PERSISTENT_BUTTONS]
    return ReplyKeyboardMarkup(
        kb,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


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
        await update.message.reply_text("У Вас нет доступа к боту")
        return ConversationHandler.END

    markup = ReplyKeyboardMarkup(
        [["Начать формирование"]],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    await update.message.reply_text(
        "Нажмите кнопку, чтобы начать формирование документа:",
        reply_markup=markup
    )
    return CHOOSING


async def choose_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "Начать формирование":
        files = [f for f in os.listdir("templates") if f.endswith(".docx")]
        rows = [[fn] for fn in files]
        markup = ReplyKeyboardMarkup(
            rows,
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(
            "Выберите шаблон документа:",
            reply_markup=markup
        )
        return CHOOSING

    context.user_data["template"] = text
    await update.message.reply_text(
        "Отлично. Теперь введите фамилию:",
        reply_markup=ReplyKeyboardRemove()
    )
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
    context.user_data["patronymic"] = "" if text.lower()=="нет" else text

    await update.message.reply_text(
        "Принято! Формирую документ…",
        reply_markup=ReplyKeyboardRemove()
    )

    tpl_name = context.user_data["template"]             # e.g. "template1.docx"
    tpl_path = os.path.join("templates", tpl_name)
    doc = DocxTemplate(tpl_path)

    raw_surname = context.user_data["surname"]
    raw_name    = context.user_data["name"]
    raw_patr    = context.user_data["patronymic"]
    surname_datv = to_dative(raw_surname)
    name_datv    = to_dative(raw_name)
    patr_datv    = to_dative(raw_patr) if raw_patr else ""

    ctx = {
        "surname_datv":    surname_datv,
        "name_datv":       name_datv,
        "patronymic_datv": patr_datv,
        "date":            date.today().strftime("%d.%m.%Y")
    }

    doc.render(ctx)

    out_dir = "output_docs"
    os.makedirs(out_dir, exist_ok=True)

    date_str = date.today().isoformat()
    base_name = os.path.splitext(tpl_name)[0]
    username = update.effective_user.username or update.effective_user.id

    short_id = uuid.uuid4().hex[:6]

    file_base = f"{date_str}_{base_name}_{username}_{short_id}"

    out_docx = os.path.join(out_dir, f"{file_base}.docx")
    out_pdf  = os.path.join(out_dir, f"{file_base}.pdf")

    doc.save(out_docx)
    convert(out_docx, out_pdf)

    with open(out_pdf, "rb") as f:
        await update.message.reply_document(f, filename=f"{file_base}.pdf")

    markup = ReplyKeyboardMarkup(
        [["Начать формирование"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "Документ готов! Если хотите создать ещё один, нажмите кнопку:",
        reply_markup=markup
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отмена. Всего доброго!")
    return ConversationHandler.END

# Запуск
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
            entry_points=[
                CommandHandler("start", start),
                MessageHandler(filters.Regex("^Начать формирование$"), start)
            ],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_template)],
            SURNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_surname)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            PATRONYMIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_patronymic)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()