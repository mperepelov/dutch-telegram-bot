import os
import pytz
from telegram.ext import JobQueue
from datetime import time
from dotenv import load_dotenv
from util.DatabaseManager import *
from util.LLMHandler import *
from util.DailyWordManager import *
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, JobQueue
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)
openai_api_key = os.getenv('OPENAI_API_KEY')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
daily_word_manager = None

TELEGRAM_TIMEOUT = 30

if not openai_api_key:
    logger.error("No OpenAI API key was found!")
elif not anthropic_api_key:
    logger.error("No Anthropic API key was found!")

db_manager = DatabaseManager()
llm_handler = LanguageModelHandler(
    openai_api_key=openai_api_key,
    anthropic_api_key=anthropic_api_key,
    db_manager=db_manager
)

async def start(update: Update, context: CallbackContext) -> None:
    welcome_message = "Hello! I'm your AI Language Tutor 🤖. Ask me anything!"
    await update.message.reply_text(welcome_message)

    # Add chat to daily word recipients
    chat_id = update.effective_chat.id
    daily_word_manager.add_chat(chat_id)

    # Store the system message if it's not already there
    if not db_manager.get_user_history():
        db_manager.store_message("system", llm_handler
    .system_message)

async def handle_message(update: Update, context: CallbackContext) -> None:
    if update.message and update.message.text:
        try:
            user_message = update.message.text
            # Get the AI response
            ai_response = await llm_handler.send_message(user_message, model_name="claude-3.7-sonnet")
            
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
    daily_word_manager = DailyWordManager(llm_handler
, application.bot)
    daily_word_manager.init_db()
    daily_word_manager.load_active_chats()

    # Schedule daily word broadcast
    job_queue = application.job_queue
    
    # Set timezone to Amsterdam (for Dutch time)
    amsterdam_tz = pytz.timezone('Europe/Amsterdam')
    target_time = time(hour=12, minute=00, tzinfo=amsterdam_tz)
    
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