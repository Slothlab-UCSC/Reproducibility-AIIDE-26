from __future__ import annotations
from ggpa.ggpa import GGPA
from action.action import EndAgentTurn, PlayCard
from config import CardType
from typing import TYPE_CHECKING
import random

if TYPE_CHECKING:
    from game import GameState
    from battle import BattleState
    from agent import Agent
    from card import Card

class NoneAgent(GGPA):

    def __init__(self):
        super().__init__("NoneAgent")

    def choose_card(self, game_state: GameState, battle_state: BattleState) -> EndAgentTurn|PlayCard:
        options = self.get_choose_card_options(game_state, battle_state)
        playable_cards = [opt for opt in options if isinstance(opt, PlayCard)]

        if not playable_cards:
            return EndAgentTurn()

        # --- Heuristic Policy ---
        # Priority 1: Play Attacks (Simple Aggro)
        for opt in playable_cards:
            card = battle_state.hand[opt.card_index]
            if card.card_type == CardType.ATTACK:
                return opt
        
        # Priority 2: Play Powers
        for opt in playable_cards:
            card = battle_state.hand[opt.card_index]
            if card.card_type == CardType.POWER:
                return opt

        # Priority 3: Play Skills (Block/Buffs)
        for opt in playable_cards:
            card = battle_state.hand[opt.card_index]
            if card.card_type == CardType.SKILL:
                return opt

        # Fallback: Random choice if no priority met
        return random.choice(playable_cards)
    
    def choose_agent_target(self, battle_state: BattleState, list_name: str, agent_list: list[Agent]) -> Agent:
        # Heuristic: Always target the enemy with the lowest HP
        try:
            # Filter for enemies (exclude player if they appear in list)
            enemies = [a for a in agent_list if a != battle_state.player]
            if enemies:
                return min(enemies, key=lambda e: e.health)
        except:
            pass
        return agent_list[0]
    
    def choose_card_target(self, battle_state: BattleState, list_name: str, card_list: list[Card]) -> Card:
        # Heuristic: Always pick the first available card
        return card_list[0]