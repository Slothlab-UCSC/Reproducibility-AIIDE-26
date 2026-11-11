from __future__ import annotations
import random
import math
from typing import TYPE_CHECKING
from ggpa.ggpa import GGPA
from action.action import EndAgentTurn, PlayCard

if TYPE_CHECKING:
    from game import GameState
    from battle import BattleState
    from agent import Agent
    from card import Card

# agent itself
class MCTSAgent(GGPA):
    def __init__(self, iterations: int = 100, exploration: float = 0.5):
        super().__init__("MCTSAgent")
        self.iterations = iterations
        self.exploration = exploration
        self.root = None

#MAIN DECISION RIGHT HERE !!!
    def choose_card(self, game_state: GameState, battle_state: BattleState) -> EndAgentTurn | PlayCard:
        self.root = TreeNode(None, None, self.exploration)

        
        for _ in range(self.iterations):
            state_copy = battle_state.copy_undeterministic() # mcts modifies game state on each iteration, we dont want that to be persistent 
            self.root.step(state_copy)

        return self.root.get_best(battle_state)

    def choose_agent_target(self, battle_state: BattleState, list_name: str, agent_list: list[Agent]) -> Agent:
        return random.choice(agent_list)

    def choose_card_target(self, battle_state: BattleState, list_name: str, card_list: list[Card]) -> Card:
        return random.choice(card_list)

    def print_tree(self):
        if self.root:
            self.root.print_tree()

#everything to do with the nodes of the mcts tree 
class TreeNode:
    def __init__(self, action, parent: TreeNode | None, c: float = 0.5):
        self.action = action
        self.parent = parent
        self.c = c
        self.children: dict = {}
        self.visits = 0
        self.total_score = 0.0
        self.unexplored_actions = []

    def step(self, state: BattleState) -> None:
        # four-phase mcts iteration: selection, expansion, simulation, backpropagation
        node = self.select(state)

        if not state.ended():
            node = node.expand(state)

        score = node.simulate(state)

        node.backpropagate(score)

    def select(self, state: BattleState) -> TreeNode:
        # traverse tree using uct until reaching unexpanded or terminal node
        node = self

        while not state.ended():
            if node.visits == 0:
                node.unexplored_actions = node._get_actions(state)
                return node

            if node.unexplored_actions:
                return node

            if not node.children:
                return node

            action = node._select_child_action()
            state.step(action)
            node = node.children[action.key()]

        return node

    def expand(self, state: BattleState) -> TreeNode:
        if not self.unexplored_actions:
            self.unexplored_actions = self._get_actions(state)

        #cant expand if there are no unexplored actions
        if not self.unexplored_actions:
            return self

        action = random.choice(self.unexplored_actions)
        self.unexplored_actions.remove(action)

        child = TreeNode(action, self, self.c)
        self.children[action.key()] = child

        state.step(action)

        return child

    def simulate(self, state: BattleState) -> float:
        while not state.ended():
            actions = self._get_actions(state)
            if not actions:
                break
            action = random.choice(actions)
            state.step(action)

        return self._evaluate_state(state)

    def backpropagate(self, score: float) -> None:
        node = self
        while node is not None:
            node.visits += 1
            node.total_score += score
            node = node.parent

    def get_best(self, state: BattleState) -> EndAgentTurn | PlayCard:
        # return most-visited child (robust child selection)
        if not self.children:
            actions = self._get_actions(state)
            return random.choice(actions) if actions else EndAgentTurn()

        best_action = max(self.children.keys(),
                         key=lambda k: self.children[k].visits)

        for action in self._get_actions(state):
            if action.key() == best_action:
                return action

        return EndAgentTurn()

    def print_tree(self, indent: int = 0) -> None:
        avg_score = self.total_score / self.visits if self.visits > 0 else 0
        action_str = self.action.key() if self.action else "Root"

        print(" " * indent + f"{action_str} {avg_score:.2f} (visits: {self.visits})")

        sorted_children = sorted(self.children.items(),
                                key=lambda x: x[1].visits,
                                reverse=True)

        for _, child in sorted_children:
            child.print_tree(indent + 2)

    def _get_actions(self, state: BattleState) -> list:
        actions = []
        for i in range(len(state.hand)):
            if state.hand[i].is_playable(state.game_state, state):
                actions.append(PlayCard(i))

        actions.append(EndAgentTurn())

        return actions

    def _select_child_action(self):
        # stochastic uct: calculate ucb values then sample via softmax
        ucb_values = {}
        for action_key, child in self.children.items():
            if child.visits == 0:
                ucb_values[action_key] = float('inf')
            else:
                exploitation = child.total_score / child.visits
                exploration = self.c * math.sqrt(math.log(self.visits) / child.visits)
                ucb_values[action_key] = exploitation + exploration

        max_ucb = max(ucb_values.values())
        if max_ucb == float('inf'):
            unvisited = [k for k, v in ucb_values.items() if v == float('inf')]
            selected_key = random.choice(unvisited)
        else:
            # softmax with temperature = 1
            exp_values = {k: math.exp(v - max_ucb) for k, v in ucb_values.items()}
            total_exp = sum(exp_values.values())
            probabilities = {k: v / total_exp for k, v in exp_values.items()}

            keys = list(probabilities.keys())
            probs = [probabilities[k] for k in keys]
            selected_key = random.choices(keys, weights=probs, k=1)[0]

        return self.children[selected_key].action

    def _evaluate_state(self, state: BattleState) -> float:
        # heuristic evaluation: win bonus + health, loss gives partial credit for damage
        if state.ended():
            result = state.get_end_result()
            if result == 1:
                health_pct = state.player.health / state.player.max_health
                return 0.8 + 0.2 * health_pct
            else:
                total_enemy_hp = sum(e.max_health for e in state.enemies)
                damage_dealt = sum(e.max_health - e.health for e in state.enemies)
                return 0.3 * (damage_dealt / total_enemy_hp)

        total_enemy_hp = sum(e.max_health for e in state.enemies)
        damage_dealt = sum(e.max_health - e.health for e in state.enemies)
        damage_ratio = damage_dealt / total_enemy_hp if total_enemy_hp > 0 else 0

        health_ratio = state.player.health / state.player.max_health

        # weighted combination prioritizing damage over health preservation
        return 0.7 * damage_ratio + 0.3 * health_ratio