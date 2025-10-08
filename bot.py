from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import os

TOKEN = "TOKEN_OF_TTeer.comBot"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f"🎉 ربات روی GitHub Codespaces فعال شد! سلام {user_name}!")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 قیمت تتر: به زودی...")

def main():
    print("🤖 ربات در حال اجرا...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("price", price_command))
    app.run_polling()

if __name__ == "__main__":
    main()