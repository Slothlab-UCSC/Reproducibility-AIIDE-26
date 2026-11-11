# /card_generator/generator.py

import random
import re
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

from grammar import Grammar

@dataclass
class EffectBlueprint:
    action: str
    target: str
    value: Union[int, str] = 0
    status: Optional[str] = None
    card_to_add: Optional[str] = None
    target_pile: Optional[str] = None

@dataclass
class CardBlueprint:
    rarity: str
    card_type: str
    effects: List[EffectBlueprint] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

class Generator:
    KNOWN_ACTIONS = {
        "DealAttackDamage", "GainBlock", "DrawCard", "AddMana", 
        "ApplyStatus", "DiscardCard", "AddCardToPile", "TargetedExhaust"
    }
    KNOWN_TARGETS = {"ENEMY", "SELF"}
    KNOWN_KEYWORDS = {"Exhaust", "Ethereal", "Innate", "XCost"}

    def __init__(self, grammar: Grammar):
        self.grammar = grammar

    def _is_non_terminal(self, symbol: str) -> bool:
        return symbol.startswith('<') and symbol.endswith('>')

    def _resolve_value(self, value_symbol: str) -> Union[int, str]:
        if value_symbol == "X":
            return "X"
            
        match = re.match(r'range\((\d+),\s*(\d+)\)', value_symbol)
        if match:
            min_val, max_val = map(int, match.groups())
            return random.randint(min_val, max_val)
        
        try:
            return int(value_symbol)
        except ValueError:
            raise ValueError(f"Invalid value symbol format: {value_symbol}")

    def generate_card_blueprint(self) -> CardBlueprint:
        expansion_result = self._expand_symbol('<card>')
        return self._parse_expansion(expansion_result)

    def _expand_symbol(self, symbol: str) -> List[str]:
        if not self._is_non_terminal(symbol):
            return [symbol]
        if symbol == "<x_value>":
             return ["X"]
        if any(v in symbol for v in ["value", "number", "damage", "block"]):
            try:
                value_range_str = self.grammar.get_expansion(symbol)[0]
                resolved_value = self._resolve_value(value_range_str)
                return [str(resolved_value)]
            except (ValueError, KeyError):
                pass
        expansion = self.grammar.get_expansion(symbol)
        
        result = []
        for sub_symbol in expansion:
            result.extend(self._expand_symbol(sub_symbol))
        return result

    def _parse_expansion(self, expansion: List[str]) -> CardBlueprint:
        rarity = expansion.pop(0)
        card_type = expansion.pop(0)
        blueprint = CardBlueprint(rarity=rarity, card_type=card_type)
        
        i = 0
        while i < len(expansion):
            token = expansion[i]
            
            if token == "And":
                i += 1
                continue            
            if token in self.KNOWN_KEYWORDS:
                blueprint.keywords.append(token.capitalize())
                i += 1
                continue
            if token in self.KNOWN_ACTIONS:
                action = token
                params = []
                j = i + 1
                while j < len(expansion) and expansion[j] not in self.KNOWN_TARGETS:
                    params.append(expansion[j])
                    j += 1
                
                if j == len(expansion):
                    break 
                
                target = expansion[j]
                effect = self._create_effect_blueprint(action, params, target)
                blueprint.effects.append(effect)                
                i = j + 1
            else:
                i += 1
        return blueprint

    def _create_effect_blueprint(self, action: str, params: List[str], target: str) -> EffectBlueprint:
        if action == "ApplyStatus":
            status = params[0].capitalize()
            value = self._resolve_value(params[1])
            return EffectBlueprint(action=action, value=value, target=target, status=status)
        
        elif action == "AddCardToPile":
            card_to_add = params[0].capitalize()
            value = self._resolve_value(params[1])
            target_pile = params[2].capitalize()
            return EffectBlueprint(action=action, value=value, target=target, card_to_add=card_to_add, target_pile=target_pile)

        elif action == "TargetedExhaust":
            value = self._resolve_value(params[0])
            target_pile = params[1].capitalize()
            return EffectBlueprint(action=action, value=value, target=target, target_pile=target_pile)

        else:
            value = self._resolve_value(params[0]) if params else 0
            return EffectBlueprint(action=action, value=value, target=target)