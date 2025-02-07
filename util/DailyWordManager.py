import logging
from datetime import time
import pytz

logger = logging.getLogger(__name__)

class DailyWordManager:
    def __init__(self, gpt_handler, bot):
        self.gpt_handler = gpt_handler
        self.bot = bot
        self.active_chats = set()  # Store chat IDs
        self.db_name = 'chat_history.db'

    def init_db(self):
        """Initialize database table for storing chat IDs"""
        import sqlite3
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS active_chats (
                chat_id INTEGER PRIMARY KEY,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        conn.commit()
        conn.close()

    def load_active_chats(self):
        """Load active chat IDs from database"""
        import sqlite3
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('SELECT chat_id FROM active_chats WHERE is_active = TRUE')
        chats = c.fetchall()
        conn.close()
        self.active_chats = set(chat[0] for chat in chats)
        logger.info(f"Loaded {len(self.active_chats)} active chats")

    def add_chat(self, chat_id):
        """Add a new chat to receive daily words"""
        import sqlite3
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO active_chats (chat_id, is_active) VALUES (?, TRUE)', (chat_id,))
        conn.commit()
        conn.close()
        self.active_chats.add(chat_id)
        logger.info(f"Added chat {chat_id} to daily word list")

    async def get_word_of_the_day(self):
        """Generate word of the day using GPT"""
        prompt = """Generate a Dutch Word of the Day in the following format:
        Word: [Dutch word]
        Translation: [English translation]
        Usage example: [Simple Dutch sentence]
        Example translation: [English translation of the sentence]
        Pronunciation tip: [Simple pronunciation guide]
        
        Choose a commonly used word that would be useful for beginners."""

        try:
            response = await self.gpt_handler.message_gpt(prompt)
            return response
        except Exception as e:
            logger.error(f"Error generating word of the day: {e}")
            return "Sorry, couldn't generate the Word of the Day. Please try again later."

    async def broadcast_word(self, context):
        """Send word of the day to all active chats"""
        word_message = await self.get_word_of_the_day()
        
        for chat_id in self.active_chats:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🎯 Dutch Word of the Day:\n\n" + word_message,
                    parse_mode='HTML'
                )
                logger.info(f"Sent word of the day to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send word to chat {chat_id}: {e}")
