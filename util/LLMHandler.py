import logging
from util.DatabaseManager import *
from openai import OpenAI
from anthropic import Anthropic

logger = logging.getLogger(__name__)

class LanguageModelHandler:
    def __init__(self, openai_api_key=None, anthropic_api_key=None, db_manager=None):
        self.openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None
        self.anthropic_client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else None
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
        # Model configurations with default settings and correct API model names
        self.model_configs = {
            "gpt-4o-mini": {
                "provider": "openai",
                "temperature": 0.8,
                "max_tokens": 2000
            },
            "gpt-4o": {
                "provider": "openai",
                "temperature": 0.7,
                "max_tokens": 2000
            },
            "gpt-4-turbo": {
                "provider": "openai",
                "temperature": 0.7,
                "max_tokens": 2000
            },
            "claude-3-opus": {
                "provider": "anthropic",
                "temperature": 0.7,
                "max_tokens": 2000,
                "api_model": "claude-3-opus-20240229"  # Specific API model name
            },
            "claude-3-sonnet": {
                "provider": "anthropic",
                "temperature": 0.7,
                "max_tokens": 2000,
                "api_model": "claude-3-sonnet-20240229"  # Specific API model name
            },
            "claude-3.5-sonnet": {
                "provider": "anthropic",
                "temperature": 0.7,
                "max_tokens": 2000,
                "api_model": "claude-3-5-sonnet-20240620"  # Specific API model name
            },
            "claude-3.7-sonnet": {
                "provider": "anthropic",
                "temperature": 0.7,
                "max_tokens": 2000,
                "api_model": "claude-3-haiku-20240307"  # Temporary fallback since 3.7 might not be available yet
            }
        }

    async def send_message(self, prompt, model_name="gpt-4o-mini", store_history=True, **kwargs):
        """
        Send a message to the specified language model
        
        Args:
            prompt (str): The user's message
            model_name (str): The model to use
            store_history (bool): Whether to store and use conversation history
            **kwargs: Additional parameters to override default model settings
            
        Returns:
            str: The model's response
        """
        
        try:
            if model_name not in self.model_configs:
                logger.error(f"Unknown model: {model_name}")
                return f"Sorry, the model '{model_name}' is not supported."
                
            model_config = self.model_configs[model_name].copy()
            # Override default settings with any provided kwargs
            for key, value in kwargs.items():
                model_config[key] = value
                
            provider = model_config.pop("provider")
            
            # Store the user's message if history is enabled
            if store_history and self.db_manager:
                self.db_manager.store_message("user", prompt)
            
            # Prepare messages with or without history
            messages = []
            if store_history and self.db_manager:
                messages = self.db_manager.get_user_history()
                logger.info(f"Using conversation history with {len(messages)} messages")
                
                # Add system message if not present
                if not messages or messages[0]["role"] != "system":
                    messages.insert(0, {"role": "system", "content": self.system_message})
            else:
                # Just use the current prompt without history
                messages = [
                    {"role": "system", "content": self.system_message},
                    {"role": "user", "content": prompt}
                ]
                logger.info("Using single message without history")
            
            # Send to appropriate provider
            if provider == "openai":
                if not self.openai_client:
                    return "OpenAI API key not provided."
                
                # Use the model name directly from the parameter for OpenAI
                actual_model = model_name
                
                logger.info(f"Sending request to OpenAI with model: {actual_model}")
                response = self.openai_client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    temperature=model_config.get("temperature", 0.7),
                    max_tokens=model_config.get("max_tokens", 1000)
                )
                ai_response = response.choices[0].message.content
                
            elif provider == "anthropic":
                if not self.anthropic_client:
                    return "Anthropic API key not provided."
                
                # Use the specific API model name from the config
                actual_model = model_config.get("api_model", model_name)
                
                # Convert OpenAI message format to Anthropic format
                anthropic_messages = []
                system_content = None
                
                for msg in messages:
                    if msg["role"] == "system":
                        system_content = msg["content"]
                    elif msg["role"] == "user":
                        anthropic_messages.append({"role": "user", "content": msg["content"]})
                    elif msg["role"] == "assistant":
                        anthropic_messages.append({"role": "assistant", "content": msg["content"]})
                
                logger.info(f"Sending request to Anthropic with model: {actual_model}")
                response = self.anthropic_client.messages.create(
                    model=actual_model,
                    messages=anthropic_messages,
                    system=system_content,
                    temperature=model_config.get("temperature", 0.7),
                    max_tokens=model_config.get("max_tokens", 1000)
                )
                ai_response = response.content[0].text
                
            else:
                return f"Unsupported provider: {provider}"
            
            # Store the AI's response if we're using history
            if store_history and self.db_manager:
                self.db_manager.store_message("assistant", ai_response)
                
            return ai_response
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error in send_message with model {model_name}: {e}")
            
            # Provide more specific error messages for common issues
            if "404" in error_message and "not_found_error" in error_message:
                return f"Model not found: The model '{model_name}' appears to be unavailable. This might be because the model name has changed or you don't have access to it. Please try a different model."
            elif "401" in error_message and "invalid x-api-key" in error_message.lower():
                return f"Authentication error: Invalid API key for {provider.capitalize()}. Please check your API key."
            else:
                return f"Sorry, I encountered an error with {model_name}: {error_message}"
    
    def get_available_models(self):
        """
        Returns a list of available models based on configured API keys
        
        Returns:
            dict: Dictionary of available models grouped by provider
        """
        available_models = {"openai": [], "anthropic": []}
        
        for model_name, config in self.model_configs.items():
            provider = config["provider"]
            
            if provider == "openai" and self.openai_client:
                available_models["openai"].append(model_name)
            elif provider == "anthropic" and self.anthropic_client:
                available_models["anthropic"].append(model_name)
                
        return available_models