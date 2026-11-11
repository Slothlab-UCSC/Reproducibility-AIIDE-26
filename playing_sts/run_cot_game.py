import os
from config import Character, Verbose
from game import GameState
from battle import BattleState
from agent import JawWorm
from g3_files.agents.cot_agent import CotAgent
from card import *
import dotenv

dotenv.load_dotenv()

assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY environment variable"

enemy = JawWorm

#scenarios = [CardRepo.get_scenario_0(), CardRepo.get_scenario_1(), CardRepo.get_scenario_2(), CardRepo.get_scenario_3(), CardRepo.get_scenario_4()]
scenarios = [CardRepo.get_scenario_0(), CardRepo.get_scenario_1()]
agent = CotAgent()

def run_scenario(scenario, enemy, agent, verbose=Verbose.LOG, ascention=0):
    scenario_name, deck = scenario
    print("--------------- Starting battle with basic CoT agent and scenario", scenario_name, "----------------")
    game_state = GameState(Character.IRON_CLAD, agent, ascention=0)
    battle_state = BattleState(
        game_state,
        enemy(game_state),
        verbose=Verbose.LOG
    )
    game_state.set_deck(deck)
    try:
        battle_state.run()
        return {
        "scenario": scenario_name,
        "result": battle_state.get_end_result(),
        "player_hp": battle_state.player.health,
        "player_max_health": battle_state.player.max_health,
        "player_mana": battle_state.mana,
        }
    except Exception as e:
        print(f"\n-----------------BATTLE CRASHED ------------------")

results = []
for scenario in scenarios:
    for i in range(1):
        output = run_scenario(scenario, enemy, agent, verbose=Verbose.LOG, ascention=0)
        print(output)
        results.append(output)

print(results)




"""
{'scenario': 'basics-bomb', 'result': 1, 'player_hp': 74, 'player_max_health': 80, 'player_mana': 1}
[{'scenario': 'starter-ironclad', 'result': 1, 'player_hp': 74, 'player_max_health': 80, 'player_mana': 0}, {'scenario': 'starter-ironclad', 'result': 1, 'player_hp': 75, 'player_max_health': 80, 'player_mana': 0}, {'scenario': 'starter-ironclad', 'result': 1, 'player_hp': 66, 'player_max_health': 80, 'player_mana': 1}, {'scenario': 'starter-ironclad', 'result': 1, 'player_hp': 74, 'player_max_health': 80, 'player_mana': 0}, {'scenario': 'starter-ironclad', 'result': 1, 'player_hp': 62, 'player_max_health': 80, 'player_mana': 2}, {'scenario': 'basics-batter-stimulate', 'result': 1, 'player_hp': 70, 'player_max_health': 80, 'player_mana': 0}, {'scenario': 'basics-batter-stimulate', 'result': 1, 'player_hp': 73, 'player_max_health': 80, 'player_mana': 2}, {'scenario': 'basics-batter-stimulate', 'result': 1, 'player_hp': 65, 'player_max_health': 80, 'player_mana': 2}, {'scenario': 'basics-batter-stimulate', 'result': 1, 'player_hp': 74, 'player_max_health': 80, 'player_mana': 0}, {'scenario': 'basics-batter-stimulate', 'result': 1, 'player_hp': 69, 'player_max_health': 80, 'player_mana': 0}, {'scenario': '1s3d-tolerate', 'result': 1, 'player_hp': 69, 'player_max_health': 80, 'player_mana': 2}, {'scenario': '1s3d-tolerate', 'result': 1, 'player_hp': 65, 'player_max_health': 80, 'player_mana': 2}, {'scenario': '1s3d-tolerate', 'result': 1, 'player_hp': 68, 'player_max_health': 80, 'player_mana': 2}, {'scenario': '1s3d-tolerate', 'result': 1, 'player_hp': 75, 'player_max_health': 80, 'player_mana': 0}, {'scenario': '1s3d-tolerate', 'result': 1, 'player_hp': 64, 'player_max_health': 80, 'player_mana': 0}, {'scenario': 'basics-bomb', 'result': 1, 'player_hp': 74, 'player_max_health': 80, 'player_mana': 2}, {'scenario': 'basics-bomb', 'result': 1, 'player_hp': 66, 'player_max_health': 80, 'player_mana': 1}, {'scenario': 'basics-bomb', 'result': 1, 'player_hp': 70, 'player_max_health': 80, 'player_mana': 1}, {'scenario': 'basics-bomb', 'result': 1, 'player_hp': 69, 'player_max_health': 80, 'player_mana': 0}, {'scenario': 'basics-bomb', 'result': 1, 'player_hp': 74, 'player_max_health': 80, 'player_mana': 1}]"""