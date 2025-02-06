import sqlite3
from util.logger import logger
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.db_name = 'chat_history.db'

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp DATETIME,
                UNIQUE(id)
            )
        ''')
        conn.commit()
        conn.close()

    def store_message(self, user_id, role, content):
        try:
            conn = sqlite3.connect(self.db_name)
            c = conn.cursor()
            
            c.execute('''
                INSERT INTO messages (user_id, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, role, content, datetime.now().isoformat()))
            
            conn.commit()
            logger.info(f"Stored message - User ID: {user_id}, Role: {role}, Content: {content[:50]}...")
            
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
        finally:
            conn.close()

    def get_user_history(self, user_id, limit=8):
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        
        c.execute('''
            SELECT role, content 
            FROM messages 
            WHERE user_id = ? 
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (user_id, limit))
        
        messages = c.fetchall()
        conn.close()
        
        return [{"role": msg[0], "content": msg[1]} for msg in messages]
