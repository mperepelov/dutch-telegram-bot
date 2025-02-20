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
        """Initialize database table for storing chat IDs"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        
        # Create active chats table
        c.execute('''
            CREATE TABLE IF NOT EXISTS active_chats (
                chat_id INTEGER PRIMARY KEY,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')

        # Create words history table
        c.execute('''
            CREATE TABLE IF NOT EXISTS dutch_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE,
                translation TEXT NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')        
        
        conn.commit()
        conn.close()

    def get_used_words(self):
        """Get list of previously used Dutch words"""
        try:
            conn = sqlite3.connect(self.db_name)
            c = conn.cursor()
            c.execute('SELECT word, translation FROM dutch_words ORDER BY date_added DESC LIMIT 100')
            words = c.fetchall()
            conn.close()
            return words
        except sqlite3.Error as e:
            logger.error(f"Error getting used words: {e}")
            return []
        
    def store_word(self, word_data):
        """Store new word in database"""
        try:
            conn = sqlite3.connect(self.db_name)
            c = conn.cursor()
            c.execute('''
                INSERT INTO dutch_words (word, translation)
                VALUES (?, ?)
            ''', (word_data['word'], word_data['translation']))
            conn.commit()
            conn.close()
            logger.info(f"Stored new word: {word_data['word']}")
        except sqlite3.Error as e:
            logger.error(f"Error storing word: {e}")

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

    def parse_word_response(self, response):
        """Parse GPT response into structured word data"""
        word_data = {
            'word': '',
            'translation': '',
            'usage_example': '',
            'example_translation': '',
            'pronunciation': ''
        }
    
        lines = response.strip().split('\n')
        logger.debug(f"Parsing response: {response}")
    
        # Simple direct mapping as format is fixed
        for line in lines:
            if line.startswith('Word: '):
                word_data['word'] = line[6:].strip()
            elif line.startswith('Translation: '):
                word_data['translation'] = line[12:].strip()
            elif line.startswith('Usage example: '):
                word_data['usage_example'] = line[14:].strip()
            elif line.startswith('Example translation: '):
                word_data['example_translation'] = line[20:].strip()
            elif line.startswith('Pronunciation tip: '):
                word_data['pronunciation'] = line[18:].strip()
    
        return word_data

    async def get_word_of_the_day(self):
        """Generate word of the day using GPT with retry logic for duplicates"""
        max_retries = 3
        current_try = 0

        while current_try < max_retries:
            try:
                # Get previously used words
                used_words = self.get_used_words()
                used_words_str = ', '.join([f"{word[0]} ({word[1]})" for word in used_words])

                prompt = f"""Generate a Dutch Word of the Day in the following format:
                Word: [Dutch word]
                Translation: [English translation]
                Usage example: [Simple Dutch sentence]
                Example translation: [English translation of the sentence]
                Pronunciation tip: [Simple pronunciation guide]

                Requirements:
                - Choose a commonly used word that would be useful for beginners
                - The word should be a single word (not a phrase)
                - Include clear phonetic pronunciation guidance
                - The example sentence should be simple and practical
                - IMPORTANT: The word MUST NOT be any of these previously used words: {used_words_str}
                - Generate a completely new word not in the above list
                """

                logger.info(f"Requesting word of the day from GPT (attempt {current_try + 1})")
                response = await self.gpt_handler.message_gpt(prompt, False)
                logger.debug(f"Raw GPT response:\n{response}")

                if not response or response == "Sorry, I encountered an error. Please try again.":
                    logger.error("Received error response from GPT handler")
                    raise ValueError("Invalid response from GPT")

                logger.info("Parsing GPT response")
                word_data = self.parse_word_response(response)
                logger.debug(f"Parsed word data: {word_data}")

                try:
                    # Try to store the word
                    self.store_word(word_data)

                    # If storage succeeded, format and return the response
                    formatted_response = f"""🎯 Dutch Word of the Day:

Word: {word_data['word']}
Translation: {word_data['translation']}
Usage example: {word_data['usage_example']}
Example translation: {word_data['example_translation']}
Pronunciation tip: {word_data['pronunciation']}"""

                    logger.info("Successfully generated and stored word of the day")
                    return formatted_response

                except sqlite3.IntegrityError as e:
                    logger.warning(f"Duplicate word found: {word_data['word']}, retrying...")
                    current_try += 1
                    if current_try >= max_retries:
                        raise Exception("Max retries reached, unable to generate unique word")
                    continue

            except Exception as e:
                logger.error(f"Error generating word of the day: {e}")
                if 'response' in locals():
                    logger.error(f"Response from GPT: {response}")
                current_try += 1
                if current_try >= max_retries:
                    return "Sorry, couldn't generate the Word of the Day. Please try again later."

        return "Sorry, couldn't generate a unique Word of the Day after multiple attempts. Please try again later."
        
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