# /card_generator/main.py

import json
import os
import argparse
import random
from typing import Dict, Any, List

from grammar import Grammar
from generator import Generator, CardBlueprint, EffectBlueprint
from balancer import Balancer
from validator import Validator

ADJECTIVES = [
    "Vicious", "Quick", "Heavy", "Piercing", "Defensive", "Calculated", "Burning", 
    "Chilling", "Sudden", "Ancient", "Forgotten", "Honed", "Careful", "Reckless",
    "Empowering", "Weakening", "Shielding", "Insightful"
]
NOUNS_ATTACK = [
    "Strike", "Bash", "Slash", "Assault", "Pummel", "Lunge", "Jab", "Rampage", "Execute"
]
NOUNS_SKILL = [
    "Defend", "Block", "Dodge", "Parry", "Maneuver", "Setup", "Think", "Plan", 
    "Recollect", "Brace", "Prepare", "Scrounge", "Fortify"
]
NOUNS_POWER = [
    "Form", "Might", "Vigor", "Presence", "Aura", "Focus", "Stance", "Perception",
    "Barricade", "Afterimage", "Enlightenment"
]

def generate_card_name(card_type: str, effects: List[EffectBlueprint]) -> str:
    adj = random.choice(ADJECTIVES)
    
    if card_type == "Attack":
        noun = random.choice(NOUNS_ATTACK)
    elif card_type == "Skill":
        noun = random.choice(NOUNS_SKILL)
    else:
        for effect in effects:
            if effect.action.upper() == "APPLYSTATUS" and effect.status in NOUNS_POWER:
                return effect.status
        noun = random.choice(NOUNS_POWER)
        
    return f"{adj} {noun}"

def create_final_json(name: str, blueprint: CardBlueprint, balance_info: Dict[str, Any]) -> Dict[str, Any]:
    effects_json = []
    for effect in blueprint.effects:
        eff_dict: Dict[str, Any] = {
            "action": effect.action.capitalize(),
            "value": effect.value,
            "target": effect.target.capitalize()
        }
        if effect.status:
            eff_dict["status"] = effect.status
        if effect.card_to_add:
            eff_dict["card_to_add"] = effect.card_to_add
        if effect.target_pile:
            eff_dict["target_pile"] = effect.target_pile
            
        effects_json.append(eff_dict)

    card_json = {
        "name": name,
        "type": blueprint.card_type,
        "cost": balance_info['cost'],
        "rarity": blueprint.rarity,
        "effects": effects_json,
    }
    return card_json


def main(args):
    output_dir = "generated_cards"
    os.makedirs(output_dir, exist_ok=True)
    
    config_dir = args.config_dir
    grammar_file = os.path.join(config_dir, "grammar.json")
    balance_file = os.path.join(config_dir, "balancing_config.json")

    try:
        grammar = Grammar(grammar_file)
        balancer = Balancer(balance_file)
    except FileNotFoundError as e:
        print(f"Error: Could not find config file. {e}")
        print(f"Please ensure 'grammar.json' and 'balancing_config.json' are in the '{config_dir}' directory.")
        return
        
    generator = Generator(grammar)
    validator = Validator()

    print(f"Generating {args.num_cards} new card(s)...\n")
    print(f"Loading grammar from: {grammar_file}")
    print(f"Loading balancing from: {balance_file}\n")
    print("=" * 50)


    for i in range(args.num_cards):
        blueprint = generator.generate_card_blueprint()
        balance_info = balancer.balance_card(blueprint)
        card_name = generate_card_name(blueprint.card_type, blueprint.effects)
        final_card_data = create_final_json(card_name, blueprint, balance_info)
        validator.validate_and_report(final_card_data, balance_info, balancer.config)

        filename = f"{card_name.replace(' ', '_').lower()}_{i+1}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(final_card_data, f, indent=2)
        
        print(f"Successfully saved card to '{filepath}'")
        print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Procedural Card Generator for MiniSlayTheSpire (V2)")
    parser.add_argument("-n", "--num_cards", type=int, default=3, help="Number of cards to generate.")
    parser.add_argument("-c", "--config_dir", type=str, default="configs", help="Path to the directory containing config files.")
    
    args = parser.parse_args()
    main(args)