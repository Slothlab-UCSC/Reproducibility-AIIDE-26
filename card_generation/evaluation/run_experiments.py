"""
run_experiments.py - Master harness for automated MiniSTS AI evaluation

Usage:
  python3 evaluation/run_experiments.py --deck deck_file.json --bot random --enemies j --runs 500 --output results.csv

- --deck: JSON file listing card names (or Python list for quick tests)
- --bot: Bot type (random, bt3, bts5, gpt-4-none, etc.)
- --enemies: Enemy string (e.g. 'j' for JawWorm)
- --runs: Number of games to simulate
- --output: CSV file to save results
"""
import argparse
import os
import sys
import json
from joblib import Parallel, delayed
import pandas as pd

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from game import GameState
from battle import BattleState
from config import Character, Verbose
from card import CardRepo, Card, CardGen
from ggpa.ggpa import GGPA
from ggpa.random_bot import RandomBot
from ggpa.backtrack import BacktrackBot
from ggpa.chatgpt_bot import ChatGPTBot
from ggpa.prompt2 import PromptOption
from agent import JawWorm, Goblin, HobGoblin, Leech


def get_card_by_name(name):
    # Try CardGen lambdas
    if hasattr(CardGen, name):
        return getattr(CardGen, name)()
    # Try generated cards
    generated = None
    try:
        generated = custom_card_generation()
    except Exception:
        pass
    if generated and name in generated:
        return generated[name]()
    raise Exception(f"Card name not found: {name}")

def load_deck(deck_path):
    if deck_path.endswith('.json'):
        with open(deck_path, 'r') as f:
            card_names = json.load(f)
        return [get_card_by_name(name) for name in card_names]
    else:
        # fallback: starter deck
        return CardRepo.get_basics()

def name_to_bot(name: str) -> GGPA:
    if name == 'random':
        return RandomBot()
    if name.startswith('bt'):
        depth = int(name[2:]) if len(name) > 2 else 3
        return BacktrackBot(depth, False)
    if name.startswith('bts'):
        depth = int(name[3:])
        return BacktrackBot(depth, True)
    if name.startswith('gpt'):
        # Example: gpt-4-none
        _, model, prompt = name.split('-')
        model_dict = {
            't3.5': ChatGPTBot.ModelName.GPT_Turbo_35,
            '4': ChatGPTBot.ModelName.GPT_4,
            't4': ChatGPTBot.ModelName.GPT_Turbo_4,
            'it3.5': ChatGPTBot.ModelName.Instruct_GPT_Turbo_35,
            'idav': ChatGPTBot.ModelName.Instruct_Davinci,
        }
        prompt_dict = {
            'none': PromptOption.NONE,
            'dag': PromptOption.DAG,
            'cot': PromptOption.CoT,
            'cotr': PromptOption.CoT_rev,
        }
        return ChatGPTBot(model_dict[model], prompt_dict[prompt], 0, False)
    raise Exception(f"Bot name not recognized: {name}")

def get_enemies(enemies: str, game_state: GameState):
    ret = []
    for char in enemies:
        if char == 'j':
            ret.append(JawWorm(game_state))
        elif char == 'g':
            ret.append(Goblin(game_state))
        elif char == 'h':
            ret.append(HobGoblin(game_state))
        elif char == 'l':
            ret.append(Leech(game_state))
        else:
            raise Exception(f"Unknown enemy code: {char}")
    return ret

def simulate_one(i, bot, deck, enemies):
    game_state = GameState(Character.IRON_CLAD, bot, 0)
    game_state.set_deck(*deck)
    battle_state = BattleState(game_state, *get_enemies(enemies, game_state), verbose=Verbose.NO_LOG)
    battle_state.run()
    return {
        'run': i,
        'bot': bot.name,
        'hp': game_state.player.health,
        'win': game_state.get_end_results() != -1
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deck', type=str, default='', help='Deck file (.json) or use starter deck')
    parser.add_argument('--bot', type=str, default='random', help='Bot type (random, bt3, bts5, gpt-4-none, etc.)')
    parser.add_argument('--enemies', type=str, default='j', help='Enemy string (e.g. j for JawWorm)')
    parser.add_argument('--runs', type=int, default=100, help='Number of games to simulate')
    parser.add_argument('--output', type=str, default='results.csv', help='CSV file to save results')
    parser.add_argument('--threads', type=int, default=4, help='Parallel threads')
    args = parser.parse_args()

    deck = load_deck(args.deck) if args.deck else CardRepo.get_basics()
    bot = name_to_bot(args.bot)
    print(f"Running {args.runs} games with bot {bot.name}, deck {[c.name for c in deck]}, enemies {args.enemies}")
    results = Parallel(n_jobs=args.threads)(delayed(simulate_one)(i, bot, deck, args.enemies) for i in range(args.runs))
    df = pd.DataFrame(results)
    df.to_csv(args.output, index=False)
    print(f"Results saved to {args.output}")

if __name__ == '__main__':
    main()
