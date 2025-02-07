import os
import pytz
from telegram.ext import JobQueue
from datetime import time
from dotenv import load_dotenv
from util.logger import logger
from util.DatabaseManager import *
from util.GPTHandler import *
from util.DailyWordManager import *
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, JobQueue


load_dotenv(override=True)
api_key = os.getenv('OPENAI_API_KEY')
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
daily_word_manager = None

TELEGRAM_TIMEOUT = 30

if not api_key:
    logger.error("No API key was found!")

db_manager = DatabaseManager()
gpt_handler = GPTHandler(api_key, db_manager)

async def start(update: Update, context: CallbackContext) -> None:
    welcome_message = "Hello! I'm your AI Language Tutor 🤖. Ask me anything!"
    await update.message.reply_text(welcome_message)

    # Add chat to daily word recipients
    chat_id = update.effective_chat.id
    daily_word_manager.add_chat(chat_id)

    # Store the system message if it's not already there
    if not db_manager.get_user_history():
        db_manager.store_message("system", gpt_handler.system_message)

async def handle_message(update: Update, context: CallbackContext) -> None:
    if update.message and update.message.text:
        try:
            user_message = update.message.text
            # Get the AI response
            ai_response = await gpt_handler.message_gpt(user_message)
            
            await update.message.reply_text(
                ai_response,
                read_timeout=TELEGRAM_TIMEOUT,
                write_timeout=TELEGRAM_TIMEOUT,
                connect_timeout=TELEGRAM_TIMEOUT,
                pool_timeout=TELEGRAM_TIMEOUT
            )
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(
                "Sorry, I encountered an error. Please try again.",
                read_timeout=TELEGRAM_TIMEOUT,
                write_timeout=TELEGRAM_TIMEOUT,
                connect_timeout=TELEGRAM_TIMEOUT,
                pool_timeout=TELEGRAM_TIMEOUT
            )
    else:
        logger.warning("Received a non-text message, ignoring.")

def setup_daily_word(application: Application):
    global daily_word_manager
    daily_word_manager = DailyWordManager(gpt_handler, application.bot)
    daily_word_manager.init_db()
    daily_word_manager.load_active_chats()

    # Schedule daily word broadcast
    job_queue = application.job_queue
    
    # Set timezone to Amsterdam (for Dutch time)
    amsterdam_tz = pytz.timezone('Europe/Amsterdam')
    target_time = time(hour=10, minute=50, tzinfo=amsterdam_tz)
    
    job_queue.run_daily(
        daily_word_manager.broadcast_word,
        time=target_time,
        days=(0, 1, 2, 3, 4, 5, 6)  # All days of the week
    )

def main():
    # Initialize the database
    db_manager.init_db()
    
    app = Application.builder().token(telegram_bot_token).concurrent_updates(True).job_queue(JobQueue()).build()

    # Set up daily word feature
    setup_daily_word(app)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()