import os
import logging
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)
api_key = os.getenv('OPENAI_API_KEY')
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

if not api_key:
    print("No API key was found - please head over to the troubleshooting notebook in this folder to identify & fix!")

openai = OpenAI()

user_history = {}

system_message = """You are a kind and patient Dutch language teacher, helping beginners learn Dutch in a simple, clear, and encouraging way.

Your teaching style is:
Easy to understand  Use simple words and short sentences.
Encouraging  Praise the learner and gently correct mistakes.
Interactive  Ask simple questions to help them practice.

Teaching Approach:
1. Translations & Explanations  Provide both Dutch and English translations.
2. Short, Simple Sentences  Avoid complex grammar at the start.
3. Practice & Encouragement  Ask follow-up questions in Dutch.
4. Corrections with Examples  If they make a mistake, correct them nicely and give an example.
5. Pronunciation Help  If needed, break down words phonetically.

Use 70% Dutch and 30% Russian to encourage immersion while keeping things understandable.
"""

async def message_gpt(user_id, prompt):
    # Check if the user already has a conversation history
    if user_id not in user_history:
        # Initialize history with the system message
        user_history[user_id] = [{"role": "system", "content": system_message}]
    
    # Append the user's message to the history
    user_history[user_id].append({"role": "user", "content": prompt})

    # Ensure the history doesn't exceed 20 messages
    if len(user_history[user_id]) > 20:
        user_history[user_id] = user_history[user_id][-20:]  # Keep only the last 20 messages

    response = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=user_history[user_id],
        temperature=0.8,
        max_tokens=300
    )

    # Get the AI response
    ai_response = response.choices[0].message.content
    
    # Append AI's response to the conversation history
    user_history[user_id].append({"role": "assistant", "content": ai_response})
    
    return ai_response


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hello! I'm your AI Language Tutor 🤖. Ask me anything!")

# Handle user messages
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    # Ensure the update contains a text message before processing
    if update.message and update.message.text:
        user_message = update.message.text
        ai_response = await message_gpt(user_id, user_message)
        await update.message.reply_text(ai_response)
    else:
        logging.warning("Received a non-text message, ignoring.")

# Main function to run the bot
def main():
    app = Application.builder().token(telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()