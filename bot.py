import os
import pytz
from telegram.ext import JobQueue
from datetime import time
from dotenv import load_dotenv
from util.DatabaseManager import *
from util.LLMHandler import *
from util.DailyWordManager import *
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, JobQueue, CallbackQueryHandler
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)
openai_api_key = os.getenv('OPENAI_API_KEY')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
daily_word_manager = None

TELEGRAM_TIMEOUT = 30

# Dict to store user preferences for model selection
user_model_preferences = {}

# Available models with friendly display names
AVAILABLE_MODELS = {
    "gpt-4o-mini": "GPT-4o Mini",
    "gpt-4o": "GPT-4o",
    "gpt-4-turbo": "GPT-4 Turbo",
    "claude-3-sonnet": "Claude 3 Sonnet",
    "claude-3-opus": "Claude 3 Opus",
    "claude-3.5-sonnet": "Claude 3.5 Sonnet",
    "claude-3.7-sonnet": "Claude 3.7 Sonnet"
}

# Default model to use
DEFAULT_MODEL = "gpt-4o-mini"

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

def get_model_selection_keyboard():
    """Create an inline keyboard for model selection"""
    keyboard = []
    
    # OpenAI models row
    openai_row = []
    for model_id in ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"]:
        openai_row.append(InlineKeyboardButton(
            AVAILABLE_MODELS[model_id], 
            callback_data=f"model_{model_id}"
        ))
    keyboard.append(openai_row)
    
    # Claude models row
    claude_row = []
    for model_id in ["claude-3-sonnet", "claude-3-opus"]:
        claude_row.append(InlineKeyboardButton(
            AVAILABLE_MODELS[model_id], 
            callback_data=f"model_{model_id}"
        ))
    keyboard.append(claude_row)
    
    # Advanced Claude models row
    advanced_claude_row = []
    for model_id in ["claude-3.5-sonnet", "claude-3.7-sonnet"]:
        advanced_claude_row.append(InlineKeyboardButton(
            AVAILABLE_MODELS[model_id], 
            callback_data=f"model_{model_id}"
        ))
    keyboard.append(advanced_claude_row)
    
    # Word of the day settings row
    keyboard.append([
        InlineKeyboardButton("📅 Subscribe to Word of the Day", callback_data="wotd_subscribe"),
        InlineKeyboardButton("🚫 Unsubscribe from Word of the Day", callback_data="wotd_unsubscribe")
    ])
    
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    
    # Set default model for this user
    user_model_preferences[chat_id] = DEFAULT_MODEL
    
    welcome_message = ("Hello! I'm your AI Dutch Language Tutor 🤖\n\n"
                       "I can help you learn Dutch through conversation and practice.\n\n"
                       "You can choose which AI model you'd like me to use for responses using the buttons below. "
                       "Different models have different strengths and speeds.")
    
    # Add chat to daily word recipients
    daily_word_manager.add_chat(chat_id)

    # Store the system message if it's not already there
    if not db_manager.get_user_history():
        db_manager.store_message("system", llm_handler.system_message)
    
    # Send welcome message with model selection keyboard
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_model_selection_keyboard(),
        read_timeout=TELEGRAM_TIMEOUT,
        write_timeout=TELEGRAM_TIMEOUT
    )

async def handle_message(update: Update, context: CallbackContext) -> None:
    if update.message and update.message.text:
        try:
            chat_id = update.effective_chat.id
            user_message = update.message.text
            
            # Get the user's preferred model or use default
            model_name = user_model_preferences.get(chat_id, DEFAULT_MODEL)
            
            # Show typing indicator
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action="typing"
            )
            
            # Get the AI response using the selected model
            ai_response = await llm_handler.send_message(
                prompt=user_message,
                model_name=model_name
            )
            
            # Add a small footer with current model info
            response_with_footer = (
                f"{ai_response}\n\n"
                f"_Using: {AVAILABLE_MODELS[model_name]}_"
            )
            
            await update.message.reply_text(
                response_with_footer,
                parse_mode="Markdown",
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

async def settings_command(update: Update, context: CallbackContext) -> None:
    """Send settings menu with model selection options"""
    await update.message.reply_text(
        "Settings:\nChoose which AI model you'd like me to use for responses:",
        reply_markup=get_model_selection_keyboard(),
        read_timeout=TELEGRAM_TIMEOUT,
        write_timeout=TELEGRAM_TIMEOUT
    )

async def button_callback(update: Update, context: CallbackContext) -> None:
    """Handle button clicks from inline keyboards"""
    query = update.callback_query
    chat_id = update.effective_chat.id
    
    # Call answer to remove the loading state of the button
    await query.answer()
    
    if query.data.startswith("model_"):
        # Extract model name from callback data
        selected_model = query.data.replace("model_", "")
        
        # Store user's model preference
        user_model_preferences[chat_id] = selected_model
        
        # Confirm selection to user
        await query.edit_message_text(
            f"Model changed to: {AVAILABLE_MODELS[selected_model]}\n\nYou can change it anytime with /settings",
            read_timeout=TELEGRAM_TIMEOUT,
            write_timeout=TELEGRAM_TIMEOUT
        )
        
    elif query.data == "wotd_subscribe":
        # Subscribe to Word of the Day
        daily_word_manager.add_chat(chat_id)
        await query.edit_message_text(
            "You've subscribed to the Dutch Word of the Day! You'll receive a new word daily at 12:00 PM Amsterdam time.",
            read_timeout=TELEGRAM_TIMEOUT,
            write_timeout=TELEGRAM_TIMEOUT
        )
        
    elif query.data == "wotd_unsubscribe":
        # Unsubscribe from Word of the Day
        daily_word_manager.remove_chat(chat_id)
        await query.edit_message_text(
            "You've unsubscribed from the Dutch Word of the Day. You can resubscribe anytime with /settings",
            read_timeout=TELEGRAM_TIMEOUT,
            write_timeout=TELEGRAM_TIMEOUT
        )

async def word_command(update: Update, context: CallbackContext) -> None:
    """Generate and send a word of the day on demand"""
    chat_id = update.effective_chat.id
    
    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=chat_id,
        action="typing"
    )
    
    # Get the user's preferred model
    model_name = user_model_preferences.get(chat_id, DEFAULT_MODEL)
    
    try:
        # Get immediate word using the user's preferred model
        word_message = await daily_word_manager.get_word_of_the_day(model_name)
        
        await update.message.reply_text(
            word_message,
            read_timeout=TELEGRAM_TIMEOUT,
            write_timeout=TELEGRAM_TIMEOUT
        )
    except Exception as e:
        logger.error(f"Error generating word of the day: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error generating the word of the day. Please try again.",
            read_timeout=TELEGRAM_TIMEOUT,
            write_timeout=TELEGRAM_TIMEOUT
        )

def setup_daily_word(application: Application):
    global daily_word_manager
    daily_word_manager = DailyWordManager(llm_handler, application.bot)
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

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("word", word_command))
    
    # Message and callback handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("🤖 Dutch Language Learning Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()