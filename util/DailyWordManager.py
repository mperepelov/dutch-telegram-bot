import logging
from datetime import time, datetime
import pytz
import sqlite3

logger = logging.getLogger(__name__)

class DailyWordManager:
    def __init__(self, gpt_handler, bot):
        self.gpt_handler = gpt_handler
        self.bot = bot
        self.active_chats = set()
        self.db_name = 'chat_history.db'

    def init_db(self):
        """Initialize database tables for storing chat IDs and daily words"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        
        # Create active chats table
        c.execute('''
            CREATE TABLE IF NOT EXISTS active_chats (
                chat_id INTEGER PRIMARY KEY,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Create daily words table
        c.execute('''
            CREATE TABLE IF NOT EXISTS daily_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                translation TEXT NOT NULL,
                usage_example TEXT NOT NULL,
                example_translation TEXT NOT NULL,
                pronunciation TEXT NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()

    def load_active_chats(self):
        """Load active chat IDs from database"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('SELECT chat_id FROM active_chats WHERE is_active = TRUE')
        chats = c.fetchall()
        conn.close()
        self.active_chats = set(chat[0] for chat in chats)
        logger.info(f"Loaded {len(self.active_chats)} active chats")

    def add_chat(self, chat_id):
        """Add a new chat to receive daily words"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO active_chats (chat_id, is_active) VALUES (?, TRUE)', (chat_id,))
        conn.commit()
        conn.close()
        self.active_chats.add(chat_id)
        logger.info(f"Added chat {chat_id} to daily word list")

    def get_existing_words(self):
        """Get list of already used Dutch words"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('SELECT word FROM daily_words')
        words = c.fetchall()
        conn.close()
        return [word[0] for word in words]

    def store_daily_word(self, word_data):
        """Store new daily word in database"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''
            INSERT INTO daily_words 
            (word, translation, usage_example, example_translation, pronunciation)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            word_data['word'],
            word_data['translation'],
            word_data['usage_example'],
            word_data['example_translation'],
            word_data['pronunciation']
        ))
        conn.commit()
        conn.close()
        logger.info(f"Stored new daily word: {word_data['word']}")

    def parse_word_response(self, response):
        """Parse GPT response into structured word data"""
        lines = response.strip().split('\n')
        word_data = {}
        
        for line in lines:
            if ': ' in line:
                key, value = line.split(': ', 1)
                key = key.strip().lower().replace(' ', '_')
                word_data[key] = value.strip()
        
        return word_data

    async def get_word_of_the_day(self):
        """Generate word of the day using GPT"""
        existing_words = self.get_existing_words()
        existing_words_str = ', '.join(existing_words)
        
        prompt = f"""Generate a Dutch Word of the Day in the following format:
        Word: [Dutch word]
        Translation: [English translation]
        Usage example: [Simple Dutch sentence]
        Example translation: [English translation of the sentence]
        Pronunciation tip: [Simple pronunciation guide]
        
        Requirements:
        - Choose a commonly used word that would be useful for beginners
        - The word must NOT be any of these already used words: {existing_words_str}
        - The word should be a single word (not a phrase)
        - Include clear phonetic pronunciation guidance
        - The example sentence should be simple and practical
        """

        try:
            response = await self.gpt_handler.message_gpt(prompt)
            word_data = self.parse_word_response(response)
            
            # Store the new word
            self.store_daily_word(word_data)
            
            # Format the response for sending
            formatted_response = f"""🎯 Dutch Word of the Day:

Word: {word_data['word']}
Translation: {word_data['translation']}
Usage example: {word_data['usage_example']}
Example translation: {word_data['example_translation']}
Pronunciation tip: {word_data['pronunciation']}"""

            return formatted_response
            
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
                    text=word_message
                )
                logger.info(f"Sent word of the day to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send word to chat {chat_id}: {e}")