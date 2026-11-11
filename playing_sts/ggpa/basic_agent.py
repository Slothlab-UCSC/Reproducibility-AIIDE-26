from __future__ import annotations
from ggpa.chatgpt_bot import ChatGPTBot
from ggpa.prompt2 import PromptOption

class BasicAgent(ChatGPTBot):

    def __init__(self, model_name: ChatGPTBot.ModelName = ChatGPTBot.ModelName.GPT_Turbo_35):

        # Call the superclass constructor with the specific configuration for a Basic Agent:
        # - prompt_option=PromptOption.NONE: Asks for a direct answer (no CoT).
        # - few_shot=0: Zero-shot learning (no examples provided).
        # - show_option_results=False: Do not include simulation results in the prompt.
        # - share_of_limit=1: Use the standard rate limit share.
        super().__init__(
            model_name=model_name,
            prompt_option=PromptOption.NONE,
            few_shot=0,
            show_option_results=False,
            share_of_limit=1
        )
        
        # Updated agent name to reflect its role as a Basic LLM Agent (No CoT or RCoT)
        self.name = f"BasicAgent-{model_name}"