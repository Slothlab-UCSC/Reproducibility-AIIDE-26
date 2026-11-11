# /card_generator/grammar.py

import json
import random
from typing import List, Dict, Any

class Grammar:
    def __init__(self, grammar_filepath: str):
        self.rules = self._load_rules(grammar_filepath)

    def _load_rules(self, filepath: str) -> Dict[str, List[List[Any]]]:
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: Grammar file not found at {filepath}")
            raise
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {filepath}")
            raise

    def get_expansion(self, non_terminal: str) -> List[str]:
        if non_terminal not in self.rules:
            raise KeyError(f"Non-terminal '{non_terminal}' not found in grammar rules.")

        productions = self.rules[non_terminal]
        weights = [prod[0] for prod in productions]
        expansions = [prod[1] for prod in productions]

        # Perform a weighted random choice
        chosen_expansion = random.choices(expansions, weights=weights, k=1)
        return chosen_expansion[0]