from game import GameState
from battle import BattleState
from config import Character, Verbose
from agent import AcidSlimeSmall, SpikeSlimeSmall, JawWorm
from card import CardGen, CardRepo
import time
from ggpa.human_input import HumanInput
from ggpa.chatgpt_bot import ChatGPTBot
from ggpa.prompt2 import PromptOption
from ggpa.backtrack import BacktrackBot
# from ggpa.backtrack_parallel import BacktrackParallelBot # Removed as file missing in upload
from ggpa.none_agent import NoneAgent
from ggpa.basic_agent import BasicAgent

def main():
    # Uncomment the agent you want to test:
    
    # 1. NoneAgent (Rule-Based, No LLM)
    # agent = NoneAgent()

    # 2. BasicAgent (LLM, Direct Prompting)
    # Note: Requires OPENAI_API_KEY in auth.py or environment variable
    agent = BasicAgent()

    # 3. Original Agents
    # agent = HumanInput(True)
    # agent = BacktrackBot(4, False)
    # agent = ChatGPTBot(ChatGPTBot.ModelName.GPT_Turbo_35, PromptOption.CoT, 0, False, 1)

    print(f"Running with agent: {agent.name}")

    game_state = GameState(Character.IRON_CLAD, agent, 0)
    game_state.set_deck(*CardRepo.get_scenario_0()[1])
    
    battle_state = BattleState(game_state, JawWorm(game_state), verbose=Verbose.LOG)
    start = time.time()
    battle_state.run()
    end = time.time()
    print(f"run ended in {end-start} seconds")

if __name__ == '__main__':
    main()