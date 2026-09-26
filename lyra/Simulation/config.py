# config.py
import os
from Knowledge_Base.knowledge_base import KnowledgeBase
from Agent.agent import Agent

# Get the project root directory (parent of Simulation directory)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Core simulation topic
TOPIC = "Gun_Control"

OPINION_AXIS = {
    "min_label": "Left-Wing (Pro-Regulation)",
    "max_label": "Right-Wing (Pro-Gun)",
    "min_value": -1.0,
    "max_value": 1.0
}

# Paths (using absolute paths based on project root)
MASTER_ROOT = os.path.join(ROOT, "Knowledge_Base", "Master_KB")
INFO_PATH = os.path.join(MASTER_ROOT, TOPIC, "info.json")

# Itialize Master knowledge base
MASTER_KB = KnowledgeBase(MASTER_ROOT, load_from_disk=True)

AGENTS = [
        Agent("Max", opinion=-0.6, attitude=-0.7, uncertainty=0.1, bias=-0.8),
        Agent("Ayrton", opinion=-0.2, attitude=0.5, uncertainty=0.8, bias=0.0),
        Agent("Oscar", opinion=-.7, attitude=0.7, uncertainty=0.7, bias=.8),
        Agent("Checo", opinion=0.1, attitude=0.1, uncertainty=0.3, bias=0.5),
        Agent("Pastor", opinion=-.2, attitude=0.1, uncertainty=0.1, bias=0.5),
        Agent("Lewis", opinion=.7, attitude=0.7, uncertainty=0.4, bias=-.7),
        Agent("Charles", opinion=0.7, attitude=0.8, uncertainty=0.2, bias=0.9),
        ]

# LLM Configuration
# For LM Studio (local): base_url="http://127.0.0.1:1234/v1", api_key="lm-studio"
# For OpenAI API: base_url="https://api.openai.com/v1", api_key="your-api-key-here"
LLM_CONFIG = {
    "base_url": "http://127.0.0.1:1234/v1",  # LM Studio default, change to "https://api.openai.com/v1" for OpenAI
    "api_key": "lm-studio",  # Change to your OpenAI API key if using OpenAI
    "model_name": "google/gemma-3n-e4b"  # Change to "gpt-4" or "gpt-3.5-turbo" for OpenAI
}