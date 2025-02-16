import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_name = 'chat_history.db'
        self.message_history_limit = 20

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                content TEXT,
                timestamp DATETIME
            )
        ''')
        conn.commit()
        conn.close()

    def store_message(self, role, content):
        # Skip storing if content contains "Dutch Word of the Day"
        if "Dutch Word of the Day" in content:
            logger.info("Skipping storage of daily word message")
            return
    
        try:
            conn = sqlite3.connect(self.db_name)
            c = conn.cursor()
            
            c.execute('''
                INSERT INTO messages (role, content, timestamp)
                VALUES (?, ?, ?)
            ''', (role, content, datetime.now().isoformat()))
            
            conn.commit()
            logger.info(f"Stored message - Role: {role}, Content: {content[:50]}...")
            
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
        finally:
            conn.close()

    def get_user_history(self):
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        
        c.execute('''
            SELECT role, content 
            FROM messages 
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (self.message_history_limit,))
        
        messages = c.fetchall()
        conn.close()
        
        return [{"role": msg[0], "content": msg[1]} for msg in messages]
