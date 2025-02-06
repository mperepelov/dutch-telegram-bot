import os
from dotenv import load_dotenv
from util.logger import logger
from util.DatabaseManager import *
from util.GPTHandler import *
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext


load_dotenv(override=True)
api_key = os.getenv('OPENAI_API_KEY')
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

if not api_key:
    logger.error("No API key was found!")

db_manager = DatabaseManager()
gpt_handler = GPTHandler(api_key, db_manager)

async def start(update: Update, context: CallbackContext) -> None:
    welcome_message = "Hello! I'm your AI Language Tutor 🤖. Ask me anything!"
    await update.message.reply_text(welcome_message)
    # Store the system message if it's not already there
    if not db_manager.get_user_history():
        db_manager.store_message("system", gpt_handler.system_message)

async def handle_message(update: Update, context: CallbackContext) -> None:
    if update.message and update.message.text:
        try:
            user_message = update.message.text
            ai_response = await gpt_handler.message_gpt(user_message)
            await update.message.reply_text(ai_response)
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text("Sorry, I encountered an error. Please try again.")
    else:
        logger.warning("Received a non-text message, ignoring.")

def main():
    # Initialize the database
    db_manager.init_db()
    
    app = Application.builder().token(telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()