import logging
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

BOT_TOKEN = "7943058540:AAGrYwNnSbbrendjDfKCCqLxpDKW4KIMJq8"

# Session store: message_id -> session dict
sessions = {}

def get_next_weekday(target_weekday: int):
    today = datetime.today()
    days_ahead = (target_weekday - today.weekday() + 7) % 7
    days_ahead = 7 if days_ahead == 0 else days_ahead
    next_day = today + timedelta(days=days_ahead)
    return next_day.strftime("%-d %B %Y")  # Use '%d' if %-d fails

def get_prompt_text(day):
    weekday_map = {"sat": 5, "sun": 6, "wed": 2}
    weekday_num = weekday_map.get(day.lower(), 5)
    date_str = get_next_weekday(weekday_num)
    return f"{date_str} {day.capitalize()} women's training attendance\n\nPlease click below to respond."

def build_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Coming", callback_data="coming")],
        [InlineKeyboardButton("❌ Not Coming", callback_data="not_coming")]
    ])

def format_response_text(session):
    responses = session["responses"]
    comments = session["comments"]

    coming_list = sorted([name for name, status in responses.items() if status == "coming"])
    not_coming_list = sorted([name for name, status in responses.items() if status == "not_coming"])

    coming_lines = [
        f"{i+1}. {name} – {comments[name]}" if name in comments else f"{i+1}. {name}"
        for i, name in enumerate(coming_list)
    ]
    not_coming_lines = [
        f"{i+1}. {name} – {comments[name]}" if name in comments else f"{i+1}. {name}"
        for i, name in enumerate(not_coming_list)
    ]

    return (
        f"{session['prompt']}\n\n"
        f"✅ *Coming*:\n" + ("\n".join(coming_lines) if coming_lines else "_No one yet_") +
        "\n\n❌ *Not Coming*:\n" + ("\n".join(not_coming_lines) if not_coming_lines else "_No one yet_")
    )

async def start_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ["sat", "sun", "wed"]:
        await update.message.reply_text("Usage: /attendance [Sat|Sun|Wed]")
        return

    day = context.args[0].capitalize()
    prompt = get_prompt_text(day)

    sent = await update.message.reply_text(
        prompt + "\n\nLoading...",
        reply_markup=build_keyboard(),
        parse_mode="Markdown"
    )

    # Initialize session
    sessions[sent.message_id] = {
        "day": day,
        "prompt": prompt,
        "chat_id": sent.chat.id,
        "message_id": sent.message_id,
        "responses": {},
        "comments": {},
        "awaiting": {}  # user_id -> (status, name)
    }

    # Update message immediately
    await context.bot.edit_message_text(
        chat_id=sent.chat.id,
        message_id=sent.message_id,
        text=format_response_text(sessions[sent.message_id]),
        reply_markup=build_keyboard(),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    name = user.first_name
    await query.answer()

    msg_id = query.message.message_id
    if msg_id not in sessions:
        return

    session = sessions[msg_id]
    session["responses"][name] = query.data
    session["comments"].pop(name, None)  # Always clear old comments

    if query.data == "not_coming":
        session["awaiting"][user.id] = (query.data, name)

        # Send DM prompt for reason
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="❌ You selected *Not Coming*. Please provide a reason.",
                parse_mode="Markdown"
            )
        except:
            await query.message.reply_text(
                f"{name}, please start a private chat with me so I can message you for a reason."
            )

    # Update group message
    await context.bot.edit_message_text(
        chat_id=session["chat_id"],
        message_id=session["message_id"],
        text=format_response_text(session),
        reply_markup=build_keyboard(),
        parse_mode="Markdown"
    )

async def handle_dm_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text.strip()

    for session in sessions.values():
        if user.id in session["awaiting"]:
            status, name = session["awaiting"].pop(user.id)

            # Store comment only for "not_coming"
            if status == "not_coming":
                session["comments"][name] = text if text else "No reason"
                await update.message.reply_text("✅ Got it! Your response has been recorded.")

            # Update group message
            await context.bot.edit_message_text(
                chat_id=session["chat_id"],
                message_id=session["message_id"],
                text=format_response_text(session),
                reply_markup=build_keyboard(),
                parse_mode="Markdown"
            )
            break

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("attendance", start_attendance))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_dm_reply))

    app.run_polling()
