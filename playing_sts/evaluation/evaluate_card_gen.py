from tqdm import tqdm
import pandas as pd
import time
import argparse
from typing import Callable
from joblib import delayed, Parallel
import sys
import os.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from game import GameState
from battle import BattleState
from config import Character, Verbose
from agent import AcidSlimeSmall, SpikeSlimeSmall, JawWorm, Goblin, HobGoblin, Leech, Enemy
from card import CardGen, Card, CardRepo
from ggpa.ggpa import GGPA
from ggpa.random_bot import RandomBot
from ggpa.backtrack import BacktrackBot
from ggpa.chatgpt_bot import ChatGPTBot
from ggpa.prompt2 import PromptOption
from ggpa.basic_agent import BasicAgent
from g3_files.agents.mcts_bot import MCTSAgent
from g3_files.agents.rcot_agent import RCotAgent, RCotConfig
from g3_files.agents.cot_agent import CotAgent

def name_to_bot(name: str, limit_share: float) -> GGPA:
    # Baseline agents
    if name == 'rndm':
        return RandomBot()
    if name == 'basic':
        return BasicAgent()

    # MCTS 
    if name == 'mcts':
        return MCTSAgent(iterations=100)
    if name.startswith('mcts-'):
        iterations = int(name.split('-')[-1])
        return MCTSAgent(iterations=iterations)

    # RCoT agents (Reverse Chain-of-Thought )
    if name == 'rcot':
        return RCotAgent(RCotConfig(prompt_option="rcot"))  # Default: openrouter/auto
    if name == 'rcot-gpt41':
        return RCotAgent(RCotConfig(model="openai/gpt-4.1", prompt_option="rcot"))
    if name == 'rcot-openrouter-auto':
        return RCotAgent(RCotConfig(model="openrouter/auto", prompt_option="rcot"))
    if name == 'rcot-claude':
        return RCotAgent(RCotConfig(model="anthropic/claude-sonnet-4.5", prompt_option="rcot"))
    if name == 'rcot-gemini':
        return RCotAgent(RCotConfig(model="google/gemini-3-pro-preview", prompt_option="rcot"))

    # RCoT agents (Free models)
    if name == 'rcot-llama-free':
        return RCotAgent(RCotConfig(model="meta-llama/llama-3.3-70b-instruct:free", prompt_option="rcot"))
    if name == 'rcot-qwen-free':
        return RCotAgent(RCotConfig(model="qwen/qwen3-4b:free", prompt_option="rcot"))
    if name == 'rcot-nemotron-free':
        return RCotAgent(RCotConfig(model="nvidia/nemotron-nano-9b-v2:free", prompt_option="rcot"))
    if name == 'rcot-gpt-oss-free':
        return RCotAgent(RCotConfig(model="openai/gpt-oss-20b:free", prompt_option="rcot"))
    if name == 'rcot-deepseek-free':
        return RCotAgent(RCotConfig(model="tngtech/deepseek-r1t2-chimera:free", prompt_option="rcot"))

    # CoT agents (Chain-of-Thought via OpenRouter)
    if name == 'cot':
        return CotAgent()  # Default: openai/gpt-4.1
    if name == 'cot-gpt41':
        return CotAgent(model_name="openai/gpt-4.1")
    if name == 'cot-openrouter-auto':
        return CotAgent(model_name="openrouter/auto")
    if name == 'cot-claude':
        return CotAgent(model_name="anthropic/claude-sonnet-4.5")
    if name == 'cot-gemini':
        return CotAgent(model_name="google/gemini-3-pro-preview")

    # CoT agents (Free models)
    if name == 'cot-llama-free':
        return CotAgent(model_name="meta-llama/llama-3.3-70b-instruct:free")
    if name == 'cot-qwen-free':
        return CotAgent(model_name="qwen/qwen3-4b:free")
    if name == 'cot-nemotron-free':
        return CotAgent(model_name="nvidia/nemotron-nano-9b-v2:free")
    if name == 'cot-gpt-oss-free':
        return CotAgent(model_name="openai/gpt-oss-20b:free")
    if name == 'cot-deepseek-free':
        return CotAgent(model_name="tngtech/deepseek-r1t2-chimera:free")

    if name == 'r':
        return RandomBot()
    if len(name) > 3 and name[0:3] == 'bts':
        depth = int(name[3:])
        return BacktrackBot(depth, True)
    if len(name) > 2 and name[0:2] == 'bt':
        depth = int(name[2:])
        return BacktrackBot(depth, False)

    # Legacy GPT bots (from paper)
    if len(name) > 10 and name[:10] == 'legacy-gpt':
        _, _, model, prompt = name.split('-')
        model_dict: dict[str, ChatGPTBot.ModelName] = {
            't3.5': ChatGPTBot.ModelName.GPT_Turbo_35,
            '4': ChatGPTBot.ModelName.GPT_4,
            't4': ChatGPTBot.ModelName.GPT_Turbo_4,
            'it3.5': ChatGPTBot.ModelName.Instruct_GPT_Turbo_35,
            'idav': ChatGPTBot.ModelName.Instruct_Davinci,
        }
        prompt_dict: dict[str, PromptOption] = {
            'none': PromptOption.NONE,
            'dag': PromptOption.DAG,
            'cot': PromptOption.CoT,
            'cotr': PromptOption.CoT_rev,
        }
        return ChatGPTBot(model_dict[model], prompt_dict[prompt], False, limit_share)
    raise Exception("Bot name not recognized")

def get_enemies(enemies: str, game_state: GameState) -> list[Enemy]:
    ret: list[Enemy] = []
    for char in enemies:
        if char == 'g':
            ret.append(Goblin(game_state))
        elif char == 'h':
            ret.append(HobGoblin(game_state))
        elif char == 'l':
            ret.append(Leech(game_state))
        else:
            raise Exception(f"Enemies not recognized for {char} in {enemies}")
    return ret

def simulate_one(index: int, bot: GGPA, new_cards: list[Card]|None, deck: list[Card], enemies: str, path: str, verbose: Verbose):
    game_state = GameState(Character.IRON_CLAD, bot, 0)
    game_state.set_deck(*deck)
    card_name = "control"
    if new_cards is not None:
        game_state.add_to_deck(*new_cards)
        card_name = "-".join([card.name for card in new_cards])
    battle_state = BattleState(game_state, *get_enemies(enemies, game_state),
                               verbose=verbose, log_filename=os.path.join(path, f'{index}_{card_name}'))
    battle_state.run()
    if isinstance(bot, ChatGPTBot):
        bot.dump_history(os.path.join(path, f'{index}_{bot.name}_history'))

    # Get agent statistics if available
    stats = {}
    if hasattr(bot, 'get_statistics'):
        stats = bot.get_statistics()

    return [
        bot.name,
        card_name,
        game_state.player.health,
        game_state.get_end_results() != -1,
        stats.get('total_requests', 0),
        stats.get('invalid_responses', 0),
        stats.get('total_tokens', 0),
        stats.get('avg_response_time', 0.0),
        stats.get('invalid_rate', 0.0)
    ]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_count', type=int)
    parser.add_argument('thread_count', type=int)
    parser.add_argument('gen_count', type=int)
    parser.add_argument('enemies', type=str)
    parser.add_argument('bot', type=str)
    parser.add_argument('--name', type=str, default="")
    parser.add_argument('--dir', type=str, default="")
    parser.add_argument('--log', action=argparse.BooleanOptionalAction)
    parser.add_argument('--gigl-dir', type=str, default="", help="Directory containing GIGL JSON card files")
    args = parser.parse_args()

    test_count = args.test_count
    thread_count = args.thread_count
    gen_count = args.gen_count
    enemies = args.enemies
    custom_name = args.name
    custom_dir = args.dir
    verbose = Verbose.LOG if args.log else Verbose.NO_LOG
    bot: GGPA = name_to_bot(args.bot, 1/thread_count)
    bot_name = bot.name

    # Load GIGL cards from JSON 
    if args.gigl_dir:
        import os
        import glob as glob_lib
        json_files = glob_lib.glob(os.path.join(args.gigl_dir, "*.json"))
        if gen_count > 0:
            json_files = json_files[:gen_count]
        cards: list[Callable[[], Card]|None] = [lambda path=f: CardRepo.load_card_from_json(path) for f in json_files]
        cards.append(None)  # Add control case
    else:
        # Use random card generation as before
        print("No GIGL directory provided, using random card generation.")
        cards: list[Callable[[], Card]|None] = [CardRepo.get_random() for _ in range(gen_count)]
        cards.append(None)
    dir_name = f'card_gen_{custom_name}_enemies_{enemies}_{test_count}_{bot_name}'
    if custom_dir != "":
        dir_name = os.path.join(custom_dir, dir_name)
    path = os.path.join('evaluation_results', dir_name)
    os.makedirs(path)
    print(f'simulating {test_count} times each for {gen_count} cards - {thread_count} threads')
    print(f'results can be found at {path}')
    results_dataset = Parallel(n_jobs=thread_count)(delayed(simulate_one)(i, bot,
                        None if cards[i//test_count] is None else [cards[i//test_count]()],
                        CardRepo.anonymize_deck(CardRepo.get_basics()), enemies, path, verbose
                        ) for i in tqdm(range(test_count * len(cards))))
    assert isinstance(results_dataset, list), "Parallel jobs have not resulted in an output of type list"
    df = pd.DataFrame(
        results_dataset,
        columns=["BotName", "CardName", "PlayerHealth", "Win", "TotalRequests", "InvalidResponses", "TotalTokens", "AvgResponseTime", "InvalidRate"]
    )
    df.to_csv(os.path.join(path, f"results.csv"), index=False)

if __name__ == '__main__':
    main()