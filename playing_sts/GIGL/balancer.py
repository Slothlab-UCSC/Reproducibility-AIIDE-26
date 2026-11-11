# /card_generator/balancer.py

import json
import math
from typing import Dict, Any, Tuple, List

from generator import CardBlueprint, EffectBlueprint

class Balancer:
    def __init__(self, config_filepath: str):
        self.config = self._load_config(config_filepath)
        self.pp_breakdown: List[Dict[str, Any]] = []

    def _load_config(self, filepath: str) -> Dict[str, Any]:
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: Balancing config file not found at {filepath}")
            raise
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {filepath}")
            raise

    def balance_card(self, blueprint: CardBlueprint) -> Dict[str, Any]:
        self.pp_breakdown = []        
        if "Xcost" in blueprint.keywords:
            self.pp_breakdown.append({
                "effect": "Global",
                "pp": 0.0,
                "reason": "X-Cost card: PP balancing is skipped."
            })
            return {
                "total_pp": 0.0,
                "cost": -1,
                "pp_breakdown": self.pp_breakdown
            }
        base_total_pp = 0.0
        for effect in blueprint.effects:
            pp, reason = self._calculate_effect_pp(effect, blueprint.card_type)
            base_total_pp += pp
            self.pp_breakdown.append({
                "effect": effect,
                "pp": pp,
                "reason": reason
            })

        total_pp = self.apply_synergy_rules(base_total_pp, blueprint)
        for keyword in blueprint.keywords:
            kw_lower = keyword.lower()
            if kw_lower in self.config['multipliers']:
                multiplier = self.config['multipliers'][kw_lower]
                reason = f"Keyword '{keyword}' Multiplier ({multiplier}x)"
                pp_change = total_pp * (multiplier - 1) 
                self.pp_breakdown.append({"effect": "Global", "pp": pp_change, "reason": reason})
                total_pp *= multiplier

        cost = self._calculate_cost(total_pp)

        return {
            "total_pp": total_pp,
            "cost": cost,
            "pp_breakdown": self.pp_breakdown
        }

    def apply_synergy_rules(self, total_pp: float, blueprint: CardBlueprint) -> float:
        effect_actions = {e.action for e in blueprint.effects}
        effect_statuses = {e.status for e in blueprint.effects if e.status}

        new_total_pp = total_pp
        if "DealAttackDamage" in effect_actions and "Vulnerable" in effect_statuses:
            damage_pp = sum(item['pp'] for item in self.pp_breakdown if item['effect'].action == "DealAttackDamage")
            synergy_bonus = damage_pp * 0.5 
            if synergy_bonus > 0:
                new_total_pp += synergy_bonus
                self.pp_breakdown.append({"effect": "Global", "pp": synergy_bonus, "reason": "Synergy: Damage + Vulnerable (0.5x Dmg PP)"})
        if "DrawCard" in effect_actions and "DiscardCard" in effect_actions:
            synergy_bonus = 4.0
            new_total_pp += synergy_bonus
            self.pp_breakdown.append({"effect": "Global", "pp": synergy_bonus, "reason": "Synergy: Draw + Discard"})            
        if "GainBlock" in effect_actions and "Weak" in effect_statuses:
            synergy_bonus = 2.0
            new_total_pp += synergy_bonus
            self.pp_breakdown.append({"effect": "Global", "pp": synergy_bonus, "reason": "Synergy: Gain Block + Apply Weak"})
        return new_total_pp

    def _calculate_effect_pp(self, effect: EffectBlueprint, card_type: str) -> Tuple[float, str]:
        action = effect.action
        if effect.value == "X":
            return 0.0, "X-Value (Handled by XCost keyword)"
        
        value = int(effect.value)
        if action in ["DrawCard", "AddMana"]:
            base_pp_per_unit = self.config['base_costs'].get(action, 1.0)
            pp = math.pow(base_pp_per_unit, value)
            reason = f"Exponential: {base_pp_per_unit}^{value}"
            return pp, reason
        if action in self.config['base_costs']:
            base_pp_per_unit = self.config['base_costs'][action]
            pp = float(value * base_pp_per_unit)
            reason = f"Base: {value} * {base_pp_per_unit}/pt"
            return pp, reason
        if action == "AddCardToPile":
            cost_key = f"{action}_{effect.card_to_add.capitalize()}"
            base_pp = self.config['base_costs'].get(cost_key, 0.0)
            pp = float(value * base_pp)
            reason = f"Action: {value} * {base_pp}/pt for {effect.card_to_add}"
            return pp, reason
        if action == "TargetedExhaust":
            cost_key = f"{action}_{effect.target_pile.capitalize()}"
            base_pp = self.config['base_costs'].get(cost_key, 0.0)
            pp = float(value * base_pp)
            reason = f"Action: {value} * {base_pp}/pt from {effect.target_pile}"
            return pp, reason
        if action == "ApplyStatus" and effect.status:
            status_name = effect.status.capitalize()
            if card_type == "Power":
                cost_key = f"{status_name}_Permanent"
                base_pp_per_unit = self.config['status_costs'].get(cost_key)                
                if base_pp_per_unit is None:
                    base_pp_per_unit = self.config['status_costs'].get(status_name, 0)
                    reason = f"Status '{status_name}' (Perm-Fallback): {value} stacks * {base_pp_per_unit}/stack"
                else:
                    reason = f"Status '{status_name}' (Permanent): {value} stacks * {base_pp_per_unit}/stack"
                
                pp = float(value * base_pp_per_unit)
                return pp, reason            
            else:
                base_pp_per_unit = self.config['status_costs'].get(status_name, 0)
                pp = float(value * base_pp_per_unit)
                reason = f"Status '{status_name}': {value} units * {base_pp_per_unit}/unit"
                return pp, reason
        
        return 0.0, "No cost defined"

    def _calculate_cost(self, total_pp: float) -> int:
        thresholds = self.config.get('cost_thresholds', {
            "0": 3.0,
            "1": 8.0,
            "2": 15.0
        })

        if total_pp <= thresholds['0']:
            return 0
        elif total_pp <= thresholds['1']:
            return 1
        elif total_pp <= thresholds['2']:
            return 2
        else:
            return 3