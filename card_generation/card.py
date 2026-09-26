from __future__ import annotations
from target.agent_target import AgentSet, ChooseAgentTarget, SelfAgentTarget, AllAgentsTarget, RandomAgentTarget
from target.card_target import CardPile, SelfCardTarget, ChooseCardTarget
from action.action import Action, AddMana, DrawCard
from action.agent_targeted_action import DealAttackDamage, ApplyStatus, AddBlock, Heal
from action.card_targeted_action import CardTargetedL1, Exhaust, AddCopy, UpgradeCard, DiscardCard
from config import CardType, Character, Rarity
from status_effecs import StatusEffectRepo, StatusEffectDefinition
from value import Value, ConstValue, UpgradableOnce, LinearUpgradable
from utility import RandomStr
from typing import TYPE_CHECKING, Callable
import json
import os
import random

if TYPE_CHECKING:
    from game import GameState
    from battle import BattleState

class Card:
    def __init__(self, name: str, card_type: CardType, mana_cost: Value, character: Character, rarity: Rarity, *actions: Action|CardTargetedL1, desc: str|None = None):
        self.name = name
        self.card_type = card_type
        self.mana_cost = mana_cost
        self.character = character
        self.rarity = rarity
        self.upgrade_count = 0
        self.mana_action = AddMana(mana_cost.negative())
        self.actions: list[Action] = []
        for action in actions:
            if isinstance(action, Action):
                self.actions.append(action)
            else:
                self.actions.append(action.By(self))
        self.desc = desc if desc is not None else " ".join([f"{action}" for action in self.actions])
    
    def play(self, game_state: GameState, battle_state: BattleState):
        assert self.is_playable(game_state, battle_state)
        self.mana_action.play(game_state.player, game_state, battle_state)
        for action in self.actions:
            action.play(game_state.player, game_state, battle_state)

    def is_playable(self, game_state: GameState, battle_state: BattleState):
        return self.mana_cost.peek() <= battle_state.mana

    def upgrade(self, times: int = 1):
        self.upgrade_count += times
        self.mana_cost.upgrade(times)
        for action in self.actions:
            for val in action.values:
                val.upgrade(times)

    def get_name(self) -> str:
        return "{}{}".format(self.name, "+"*self.upgrade_count)
    
    def __repr__(self) -> str:
        return "{}-cost:{}-{}-{}\n-".format(self.get_name(), self.mana_cost.peek(), self.card_type, self.rarity) + \
            "\n-".join(['' + action.__repr__() for action in self.actions])

    def get_description(self) -> str:
        return self.desc

class CardGen:
    Strike = lambda: Card("Strike", CardType.ATTACK, ConstValue(1), Character.IRON_CLAD, Rarity.STARTER, DealAttackDamage(UpgradableOnce(6, 9)).To(ChooseAgentTarget(AgentSet.ENEMY)))
    Defend = lambda: Card("Defend", CardType.SKILL, ConstValue(1), Character.IRON_CLAD, Rarity.STARTER, AddBlock(UpgradableOnce(5, 8)).To(SelfAgentTarget()))
    Searing_Blow = lambda: Card("SearingBlow", CardType.ATTACK, ConstValue(2), Character.IRON_CLAD, Rarity.UNCOMMON, DealAttackDamage(LinearUpgradable(12, 4)).To(ChooseAgentTarget(AgentSet.ENEMY)))
    Bash = lambda: Card("Bash", CardType.ATTACK, ConstValue(2), Character.IRON_CLAD, Rarity.STARTER, DealAttackDamage(UpgradableOnce(8, 10)).And(ApplyStatus(UpgradableOnce(2, 3), StatusEffectRepo.VULNERABLE)).To(ChooseAgentTarget(AgentSet.ENEMY)))
    BashStar = lambda: Card("Bash", CardType.ATTACK, ConstValue(2), Character.IRON_CLAD, Rarity.STARTER, DealAttackDamage(UpgradableOnce(8, 10)).To(ChooseAgentTarget(AgentSet.ENEMY)).And(ApplyStatus(UpgradableOnce(2, 3), StatusEffectRepo.VULNERABLE).To(ChooseAgentTarget(AgentSet.ENEMY))))
    Anger = lambda: Card("Anger", CardType.ATTACK, ConstValue(0), Character.IRON_CLAD, Rarity.COMMON, DealAttackDamage(UpgradableOnce(6, 8)).To(ChooseAgentTarget(AgentSet.ENEMY)), AddCopy(CardPile.DISCARD).To(SelfCardTarget()))
    # TODO upgrade for Armament
    Armaments = lambda: Card("Armament", CardType.SKILL, ConstValue(1), Character.IRON_CLAD, Rarity.COMMON, AddBlock(ConstValue(5)).To(SelfAgentTarget()), UpgradeCard().To(ChooseCardTarget(CardPile.HAND)))
    Cleave = lambda: Card("Cleave", CardType.ATTACK, ConstValue(1), Character.IRON_CLAD, Rarity.COMMON, DealAttackDamage(UpgradableOnce(8, 11)).To(AllAgentsTarget(AgentSet.ENEMY)))
    Impervious = lambda: Card("Impervious", CardType.SKILL, ConstValue(2), Character.IRON_CLAD, Rarity.RARE, AddBlock(UpgradableOnce(30, 40)).To(SelfAgentTarget()), Exhaust().To(SelfCardTarget()))
    # TODO this doesn't work yet, here for reference
    Survivor = lambda: Card("Survivor", CardType.SKILL, ConstValue(1), Character.SILENT, Rarity.COMMON, AddBlock(ConstValue(8)).To(SelfAgentTarget()), DiscardCard().To(ChooseCardTarget(CardPile.HAND)))
    # NEW CARDS
    Stimulate = lambda: Card("Stimulate", CardType.SKILL, ConstValue(1), Character.IRON_CLAD, Rarity.COMMON, ApplyStatus(ConstValue(4), StatusEffectRepo.VIGOR).To(SelfAgentTarget()))
    Batter = lambda: Card("Batter", CardType.SKILL, ConstValue(1), Character.IRON_CLAD, Rarity.COMMON, DealAttackDamage(ConstValue(0), ConstValue(10)).To(ChooseAgentTarget(AgentSet.ENEMY)))
    Tolerate = lambda: Card("Tolerate", CardType.POWER, ConstValue(3), Character.IRON_CLAD, Rarity.COMMON, ApplyStatus(ConstValue(1), StatusEffectRepo.TOLERANCE).To(SelfAgentTarget()), desc="Gain 1 block every turn and increase this gain by 2.")
    Bomb = lambda: Card("Bomb", CardType.SKILL, ConstValue(2), Character.IRON_CLAD, Rarity.COMMON, ApplyStatus(ConstValue(3), StatusEffectRepo.BOMB).To(SelfAgentTarget()), desc="At the end of 3 turns, deal 40 damage to all enemies.")
    Suffer = lambda: Card("Suffer", CardType.ATTACK, ConstValue(1), Character.IRON_CLAD, Rarity.STARTER, DealAttackDamage(UpgradableOnce(15, 30)).To(ChooseAgentTarget(AgentSet.ENEMY)))
    # 244 Test Cards
    Thinking = lambda: Card("Thinking", CardType.SKILL, ConstValue(1), Character.IRON_CLAD, Rarity.UNCOMMON, DrawCard(ConstValue(2)))

class CardRepo:
    @staticmethod
    def get_random() -> Callable[[], Card]:
        import random, string
        import numpy as np
        def get_random_pile():
            return random.choice([CardPile.HAND, CardPile.DISCARD, CardPile.DRAW])
        def get_random_target():
            return random.choice([AllAgentsTarget(AgentSet.ALL), AllAgentsTarget(AgentSet.ENEMY), SelfAgentTarget(), ChooseAgentTarget(AgentSet.ENEMY), RandomAgentTarget(AgentSet.ENEMY)])
        def get_deal_damage(cost: Value) -> Action:
            val = random.randint(0, int((cost.peek() + 1) * 10))
            multi = 1 if random.randint(0, 3) != 0 else random.randint(2, 10)
            target = get_random_target()
            return DealAttackDamage(ConstValue(int(val/multi)), ConstValue(multi)).To(target)
        def get_add_copy():
            return AddCopy(CardPile.DISCARD).To(SelfCardTarget())
        def get_add_block(cost: Value) -> Action:
            val = random.randint(0, int((cost.peek() + 1) * 7))
            return AddBlock(ConstValue(val)).To(get_random_target())
        def get_apply_status(cost: Value) -> Action:
            val = random.randint(0, int((cost.peek() + 1) * 5))
            ses: list[StatusEffectDefinition] = [StatusEffectRepo.STRENGTH, StatusEffectRepo.VIGOR, StatusEffectRepo.VULNERABLE, StatusEffectRepo.WEAK]
            status = random.choice(ses)
            return ApplyStatus(ConstValue(val), status).To(get_random_target())
        def get_random_action(cost: Value) -> Action|CardTargetedL1:
            return random.choice([
                get_deal_damage(cost), get_add_copy(), get_add_block(cost), get_apply_status(cost)
                ])
        name = RandomStr.get_random()
        type = random.choice([CardType.ATTACK, CardType.POWER, CardType.SKILL])
        p = np.array([1, 1, 0.8, 0.3, 0.1, 0.05])
        p /= sum(p)
        cost = np.random.choice([0, 1, 2, 3, 4, 5], p=p)
        char = Character.IRON_CLAD
        rarity = Rarity.COMMON
        acs: list[CardTargetedL1|Action] = []
        p = np.array([1, 0.5, 0.1])
        p /= sum(p)
        ac_count = np.random.choice([1, 2, 3], p=p)
        if type == CardType.ATTACK:
            acs.append(get_deal_damage(ConstValue(int(cost/ac_count))))
        while len(acs) != ac_count:
            acs.append(get_random_action(ConstValue(int(cost/ac_count))))
        if random.randint(0, 3) == 0:
            acs.append(Exhaust().To(SelfCardTarget()))
        # TODO check copy
        gen = lambda: Card(name, type, ConstValue(cost), char, rarity, *acs)
        return gen

    @staticmethod
    def get_starter(character: Character) -> list[Card]:
        starter: list[Card] = []
        if character == Character.IRON_CLAD:
            starter += [CardGen.Strike() for _ in range(4)] #originally 5
            starter += [CardGen.Defend() for _ in range(4)]
            starter += [CardGen.Bash() for _ in range(1)]
            starter += [CardGen.Thinking() for _ in range(1)]
            return starter
        else:
            raise Exception("Undefined started deck for character {}.".format(character))
        
    @staticmethod
    def get_basics() -> list[Card]:
        deck: list[Card] = []
        deck += [CardGen.Strike() for _ in range(5)]
        deck += [CardGen.Defend() for _ in range(4)]
        return deck
    
    @staticmethod
    def get_scenario_0() -> tuple[str, list[Card]]:
        deck: list[Card] = CardRepo.get_starter(Character.IRON_CLAD)
        return "starter-ironclad", deck

    @staticmethod
    def get_scenario_1() -> tuple[str, list[Card]]:
        deck: list[Card] = CardRepo.get_basics()
        deck += [CardGen.Batter(), CardGen.Stimulate()]
        return "basics-batter-stimulate", deck
    
    @staticmethod
    def get_scenario_2() -> tuple[str, list[Card]]:
        deck: list[Card] = []
        deck += [CardGen.Strike() for _ in range(1)]
        deck += [CardGen.Defend() for _ in range(3)]
        deck += [CardGen.Tolerate()]
        return "1s3d-tolerate", deck

    @staticmethod
    def get_scenario_3() -> tuple[str, list[Card]]:
        deck: list[Card] = CardRepo.get_basics()
        deck += [CardGen.Bomb()]
        return "basics-bomb", deck

    @staticmethod
    def get_scenario_4() -> tuple[str, list[Card]]:
        deck: list[Card] = CardRepo.get_basics()
        deck += [CardGen.Suffer()]
        return "basics-suffer", deck
    
    # CMPM 244 Card Implementation
    @staticmethod
    def get_generated_scenario() -> tuple[str, list[Card]]:
        deck: list[Card] = []
        gen_cards = custom_card_generation()

        # Making sure that we have at least 20 generated cards to make a complete 20-card deck. If more are made, then we get to choose randomly from the pool
        if(len(gen_cards) < 20):
            raise ValueError(f"Generation Error: There must be at LEAST 20 cards to generate, currently only {len(gen_cards)} available.")
        
        # Choosing 20 unique cards from generated list out of X generated cards (must have at least 20 to choose from)
        selected_cards = random.sample(list(gen_cards.values()), 20)
        for card in selected_cards:
            deck += [card() for _ in range(1)] # one copy of each selected card
        
        return "pcg-deck", deck
    
    @staticmethod
    def anonymize_scenario(scenario: tuple[str, list[Card]]) -> tuple[str, list[Card]]:
        name, cards = scenario
        cards = CardRepo.anonymize_deck(cards)
        return name, cards
    
    @staticmethod
    def anonymize_deck(cards: list[Card]):
        for card in cards:
            card.name = RandomStr.get_hashed(card.name)
        return cards
    
# CMPM 244 Card Generation -> Executable Card Implementation
def main():
    cards = custom_card_generation()
    print("Testing Generated Cards:", cards)

def custom_card_generation():
    card_dict = {}

    directory = 'GIGL/generated_cards' # NOTE: ensure this path is correct based on where the generated cards are stored, will fail if no cards are generated beforehand
    for file in os.listdir(directory):
        with open(os.path.join(directory, file)) as f:
            card_json = json.load(f)

            # Lambda needs local loop variables to bind it so it doesn't copy for later lambda calls
            # Card format: Card(name, card type, mana cost, player, rarity, action)
            generated_card = (lambda card=card_json: Card(
                card['name'],
                CardType[card['type'].upper()],
                ConstValue(card['cost']),
                Character.IRON_CLAD,
                Rarity[card['rarity'].upper()],
                generated_actions(card['effects'])
            ))

            card_dict[card_json['name']] = generated_card

    return card_dict

# Given the card, we attempt to translate action description -> executable actions
# Card JSON Format: Action, Value, Target, (Status)
# Currently Supported Actions:
# * Deal Damage
# * Draw Card
# * Discard Card
# * Apply status ailment
# * - weak, vulnerable, vigor, strength
# * GainBlock
# * Exhaust
# * Heal
# * Mana
def generated_actions(effects):
    exec = None
    for effect in effects:
        match effect['action'].upper():
            case "ADDMANA":
                exec = AddMana(ConstValue(effect['value'])) if exec is None else exec.And(AddMana(ConstValue(effect['value'])))
            case "APPLYSTATUS":
                exec = ApplyStatus(ConstValue(effect['value']), assign_status(effect['status'])).To(assign_target(effect['target'])) if exec is None else exec.And(ApplyStatus(ConstValue(effect['value']), assign_status(effect['status'])).To(assign_target(effect['target'])))
            case "DEALATTACKDAMAGE":
                exec = DealAttackDamage(ConstValue(effect['value'])).To(assign_target(effect['target'])) if exec is None else exec.And(DealAttackDamage(ConstValue(effect['value'])).To(assign_target(effect['target'])))
            case "DISCARDCARD":
                exec = DiscardCard().To(assign_target(effect['target'])) if exec is None else exec.And(DiscardCard().To(assign_target(effect['target'])))
            case "DRAWCARD":
                if(effect['target'].upper() == 'SELF'):
                    exec = DrawCard(ConstValue(effect['value'])) if exec is None else exec.And(DrawCard(ConstValue(effect['value'])))
            case "EXHAUST":
                exec = Exhaust().To(assign_target(effect['target'])) if exec is None else exec.And(Exhaust().To(assign_target(effect['target'])))
            case "GAINBLOCK":
                exec = AddBlock(ConstValue(effect['value'])).To(assign_target(effect['target'])) if exec is None else exec.And(AddBlock(ConstValue(effect['value'])).To(assign_target(effect['target'])))
            case "HEAL":
                exec = Heal(ConstValue(effect['value'])).To(assign_target(effect['target'])) if exec is None else exec.And(Heal(ConstValue(effect['value'])).To(assign_target(effect['target'])))
    return exec

def assign_target(t):
    if(t.upper() == 'SELF'):
        return SelfAgentTarget()
    if(t.upper() == 'ENEMY'):
        return ChooseAgentTarget(AgentSet.ENEMY)
    
def assign_status(s):
    if(s.upper() == 'VULNERABLE'):
        return StatusEffectRepo.VULNERABLE
    if(s.upper() == 'WEAK'):
        return StatusEffectRepo.WEAK
    if(s.upper() == 'STRENGTH'):
        return StatusEffectRepo.STRENGTH
    if(s.upper() == 'VIGOR'):
        return StatusEffectRepo.VIGOR
    if(s.upper() == 'TOLERANCE'):
        return StatusEffectRepo.TOLERANCE

if __name__ == '__main__':
    main()