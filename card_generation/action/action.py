from __future__ import annotations
from value import Value, ConstValue
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from battle import BattleState
    from game import GameState
    from agent import Agent

class Action:
    def __init__(self, *values: Value) -> None:
        self.values = values

    def And(self, other: Action) -> Action:
        return AndAction(self, other)
    
    def play(self, by: Agent, game_state: GameState, battle_state: BattleState) -> None:
        raise NotImplementedError("The \"play\" method is not implemented for action {}.".format(self.__class__.__name__))

    def __repr__(self) -> str:
        return self.__class__.__name__ + "({})".format('-'.join([value.__repr__() for value in self.values]))
    
class AndAction(Action):
    def __init__(self, *actions: Action):
        super().__init__(*[value for action in actions for value in action.values])
        self.actions = actions
    
    def play(self, by: Agent, game_state: GameState, battle_state: BattleState):
        for action in self.actions:
            action.play(by, game_state, battle_state)
    
    def __repr__(self) -> str:
        return ' and '.join([action.__repr__() for action in self.actions])

class AddMana(Action):
    def __init__(self, val: Value):
        super().__init__(val)
        self.val = val
    
    def play(self, by: Agent, game_state: GameState, battle_state: BattleState) -> None:
        battle_state.add_to_mana(self.val.get())
    
    def __repr__(self) -> str:
        return f"Add {self.val.get()} Mana to your mana pool"

# Added Draw Functionality for 244 (inspured by Markus's CMPM 146 Class Assignment)
class DrawCard(Action):
    def __init__(self, val: Value = ConstValue(1)):
        super().__init__(val)
        self.val = val
    
    def play(self, by: Agent, game_state: GameState, battle_state: BattleState) -> None:
        for _ in range(self.val.get()):
            battle_state.draw_one()

    def __repr__(self) -> str:
        if(self.val.get() == 1):
            return "Draw a card to your hand"
        else:
            return f"Draw {self.val.get()} cards to your hand"

class PlayCard(Action):
    def __init__(self, card_index: int):
        super().__init__()
        self.card_index = card_index
    
    def get_card_index(self):
        return self.card_index

    def play(self, by: Agent, game_state: GameState, battle_state: BattleState) -> None:
        battle_state.play_card(self.card_index)
    
    def __repr__(self) -> str:
        return f"Play card {self.card_index} from your hand"

class NoAction(Action):
    def play(self, by: Agent, game_state: GameState, battle_state: BattleState) -> None:
        pass

class EndAgentTurn(Action):
    def play(self, by: Agent, game_state: GameState, battle_state: BattleState) -> None:
        battle_state.end_agent_turn()
    
    def __repr__(self) -> str:
        return "End turn"