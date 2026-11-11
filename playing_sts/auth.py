import os
from dotenv import load_dotenv

load_dotenv()
GPT_AUTH = os.getenv('OPENAI_API_KEY', '') # Load from .env file or use empty string as fallback
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '') # Load OpenRouter API key from .env
