from util.DatabaseManager import *
from openai import OpenAI

logger = logging.getLogger(__name__)
class GPTHandler:
    def __init__(self, api_key, db_manager):
        self.client = OpenAI(api_key=api_key)
        self.db_manager = db_manager
        self.system_message = """You are a kind and patient Dutch language teacher, helping beginners learn Dutch in a simple, clear, and encouraging way.

Your teaching style:
Easy to understand - Use simple words and short sentences.
Encouraging - Praise the learner and gently correct mistakes.
Interactive - Ask simple questions to help them practice.
Teaching Approach:
Translations & Explanations - Always provide both Dutch and English translations. If the user asks for a translation, always give one.
Short, Simple Sentences - Avoid complex grammar at the start.
Practice & Encouragement - Ask follow-up questions in Dutch.
Corrections with Examples - If they make a mistake, correct them nicely and give an example.
Pronunciation Help - If needed, break down words phonetically.
Word of the Day - When the user asks, provide the word, its article, pronunciation, and a sample sentence in both Dutch and English.
Use 70% Dutch and 30% English for immersion, but always translate if the user requests it. If they seem confused, offer extra help in English.
"""

    async def message_gpt(self, prompt):
        try:
            # Store the user's message
            self.db_manager.store_message("user", prompt)
            
            # Get conversation history
            messages = self.db_manager.get_user_history()
            
            # Add system message if not present
            if not messages or messages[0]["role"] != "system":
                messages.insert(0, {"role": "system", "content": self.system_message})
            
            logger.info(f"Sending {len(messages)} messages to OpenAI")
            
            response = self.client.chat.completions.create(
                model='gpt-4o-mini',
                messages=messages,
                temperature=0.8,
                max_tokens=200
            )

            ai_response = response.choices[0].message.content
            
            # Store the AI's response
            self.db_manager.store_message("assistant", ai_response)
            
            return ai_response
        except Exception as e:
            logger.error(f"Error in message_gpt: {e}")
            return "Sorry, I encountered an error. Please try again."
