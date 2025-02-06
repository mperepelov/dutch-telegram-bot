from util.logger import logger
from util.DatabaseManager import *
from openai import OpenAI

class GPTHandler:
    def __init__(self, api_key, db_manager):
        self.client = OpenAI(api_key=api_key)
        self.db_manager = db_manager
        self.system_message = """You are a kind and patient Dutch language teacher, helping beginners learn Dutch in a simple, clear, and encouraging way.

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

Use 70% Dutch and 30% English to encourage immersion while keeping things understandable.
"""

    async def message_gpt(self, user_id, prompt):
        try:
            # Store the user's message
            self.db_manager.store_message(user_id, "user", prompt)
            
            # Get conversation history
            messages = self.db_manager.get_user_history(user_id)
            
            # Add system message if not present
            if not messages or messages[0]["role"] != "system":
                messages.insert(0, {"role": "system", "content": self.system_message})
            
            logger.info(f"Sending {len(messages)} messages to OpenAI for user {user_id}")
            
            response = self.client.chat.completions.create(
                model='gpt-4o-mini',
                messages=messages,
                temperature=0.8,
                max_tokens=300
            )

            ai_response = response.choices[0].message.content
            
            # Store the AI's response
            self.db_manager.store_message(user_id, "assistant", ai_response)
            
            return ai_response
        except Exception as e:
            logger.error(f"Error in message_gpt: {e}")
            return "Sorry, I encountered an error. Please try again."
