"""
API Configuration for AoE2 Scenario Generator
Store your OpenRouter API key and other settings here.
"""

# OpenRouter API Configuration
# Load from environment variable only
import os

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# API Settings
DEFAULT_MODEL = ""
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4000
REQUEST_TIMEOUT = 60

# Alternative models you can use
ALTERNATIVE_MODELS = [
    "openai/gpt-4",
    "anthropic/claude-3-opus", 
    "meta-llama/llama-3.1-70b-instruct",
    "google/gemini-pro"
]

# Output settings
DEFAULT_OUTPUT_DIR = "scenarios"
AOE2_SCENARIO_PATH = "C:/Users/USER001/Games/Age of Empires 2 DE/76561198844555824/resources/_common/scenario"

def get_api_key():
    """Get the API key from this configuration file"""
    return OPENROUTER_API_KEY

def get_api_settings():
    """Get all API settings"""
    return {
        "api_key": OPENROUTER_API_KEY,
        "model": DEFAULT_MODEL,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "timeout": REQUEST_TIMEOUT
    } 
