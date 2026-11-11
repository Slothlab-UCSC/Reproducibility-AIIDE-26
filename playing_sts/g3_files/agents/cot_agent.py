from __future__ import annotations
import time
import random
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass, field

from openai import OpenAI
import os
import re

from ggpa.ggpa import GGPA
from ggpa.prompt2 import get_agent_target_prompt, get_card_target_prompt
from action.action import EndAgentTurn, PlayCard
from auth import OPENROUTER_API_KEY

if TYPE_CHECKING:
    from game import GameState
    from battle import BattleState
    from agent import Agent
    from card import Card


@dataclass
class CotConfig:
    model: str
    temperature: float = 0.2
    max_tokens: int = 500
    anonymize_cards: bool = True
    retry_limit: int = 1
    prompt_option: str = "Cot"


@dataclass
class CotStatistics:
    total_requests: int = 0
    invalid_responses: int = 0
    total_tokens: int = 0
    response_times: list[float] = field(default_factory=list)

    @property
    def avg_response_time(self) -> float:
        return sum(self.response_times) / len(self.response_times) if self.response_times else 0.0

    @property
    def invalid_rate(self) -> float:
        return (self.invalid_responses / self.total_requests * 100) if self.total_requests else 0.0


class CotAgent(GGPA):

    def __init__(self, model_name: str = "openai/gpt-4.1", config: Optional[CotConfig] = None) -> None:
        self.config = config or CotConfig(model=model_name)
        self.model_name = model_name

        self.system_prompt = (
            "You are an expert card game strategist.\n"
            "Analyze the game state, your hand, and enemy intent.\n"
            "You must choose ONLY ONE card from the list options.\n"
            "Your goal is to WIN the game effectively.\n"
        )

        # Determine short name for testing
        model_short_names = {
            "openai/gpt-4.1": "gpt41",
            "openrouter/auto": "or-auto",
            "anthropic/claude-sonnet-4.5": "claude",
            "google/gemini-3-pro-preview": "gemini",
            "meta-llama/llama-3.3-70b-instruct:free": "llama-free",
            "qwen/qwen3-4b:free": "qwen-free",
            "nvidia/nemotron-nano-9b-v2:free": "nemotron-free",
            "openai/gpt-oss-20b:free": "gpt-oss-free",
            "tngtech/deepseek-r1t2-chimera:free": "deepseek-free",
        }
        short_name = model_short_names.get(model_name, model_name.replace("/", "-").replace(":", "-"))

        super().__init__(name=f"CoT-{short_name}")

        # All models use OpenRouter API so we can have lazy initialization for pickling during testing
        self._client = None

        self.stats = CotStatistics()
        self.card_anonymization_map = {}

    @property
    def client(self):
        if self._client is None:
            try:
                self._client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=OPENROUTER_API_KEY,
                )
            except Exception as e:
                print(f"\nAPI KEY ERROR: {type(e)}, {e}")
                raise
        return self._client

    def _anonymize_card_name(self, card_name: str) -> str:
        if not self.config.anonymize_cards:
            return card_name

        if card_name not in self.card_anonymization_map:
            chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
            self.card_anonymization_map[card_name] = ''.join(random.choice(chars) for _ in range(6))

        return self.card_anonymization_map[card_name]
    #from the old agents used in the paper 
    def _build_game_context(self, game_state: GameState, battle_state: BattleState) -> str:
        lines = ["=== GAME RULES ==="]
        lines.append("in this game, the player has a deck of cards.")
        lines.append("at the start of every turn, you draw cards from your draw pile.")
        lines.append("when the draw pile is empty, the discard pile is shuffled back into the draw pile.")
        lines.append(f"at the start of every turn, you gain {game_state.max_mana} mana.")
        lines.append("you can play cards by spending mana equal to the card's cost.")
        lines.append("after playing a card, it moves to the discard pile.")
        lines.append("when you end your turn, enemies perform their intended action.")
        lines.append("enemy attacks reduce your block first, then your hp.")
        lines.append("block is removed at the start of your turn.")
        lines.append("")
        lines.append("=== DECK COMPOSITION ===")

        all_cards = battle_state.draw_pile + battle_state.discard_pile + battle_state.hand + battle_state.exhaust_pile
        card_counts = {}
        for card in all_cards:
            name = self._anonymize_card_name(card.name) # we still decided to do this after the presentation in class 
            if name not in card_counts:
                card_counts[name] = {'count': 0, 'card': card}
            card_counts[name]['count'] += 1

        for name, info in sorted(card_counts.items()):
            card = info['card']
            cost = card.mana_cost.peek()
            desc = card.get_description() if hasattr(card, 'get_description') else str(card)
            lines.append(f"{name} (cost {cost}): {desc} [{info['count']}x in deck]")

        return "\n".join(lines)

    def _build_game_state(self, game_state: GameState, battle_state: BattleState,
                         options: list[PlayCard | EndAgentTurn]) -> str:
        player = battle_state.player
        lines = [f"\n=== TURN {battle_state.turn} STATE ==="]
        lines.append(f"mana: {battle_state.mana}/{game_state.max_mana}")
        lines.append(f"player: {player.health}/{player.max_health} hp, {player.block} block")
        lines.append(f"status effects: {repr(player.status_effect_state)}")
        lines.append("")

        lines.append("enemies:")
        for i, enemy in enumerate(battle_state.enemies):
            intent = enemy.get_intention(game_state, battle_state)
            lines.append(f"  {i}. {enemy.name}: {enemy.health}/{enemy.max_health} hp, {enemy.block} block")
            lines.append(f"     intent: {intent}")

        lines.append("")
        lines.append("=== YOUR OPTIONS ===")
        for i, option in enumerate(options):
            if isinstance(option, PlayCard):
                card = battle_state.hand[option.card_index]
                name = self._anonymize_card_name(card.name)
                cost = card.mana_cost.peek()
                desc = card.get_description() if hasattr(card, 'get_description') else str(card)
                lines.append(f"{i}. play {name} (cost {cost}): {desc}")
            else:
                lines.append(f"{i}. end turn")

        return "\n".join(lines)

    def _build_request(self, num_options: int) -> str:
        if self.config.prompt_option != "Cot":
            raise ValueError(f"CotAgent only supports prompt_option='Cot', got '{self.config.prompt_option}'")
#Cot prompt
        lines = ["\n=== DECISION ==="]
        lines.append("In the first paragraph, give the explanation of which option you think is best.")
        lines.append(f"After that, starting at the second paragraph, write only the index of the option you want to take.")
        lines.append(f"It should be one of the provided options (0-{num_options-1}).")
        lines.append("Only print this number in a single line for the second paragraph, and nothing else.")

        return "\n".join(lines)

    def _parse_response(self, content: str, max_index: int) -> Optional[int]:
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        if len(paragraphs) < 2:
            lines = [l.strip() for l in content.split('\n') if l.strip()]
            if len(lines) >= 2:
                card_index = lines[-1]
            else:
                card_index = content.strip().split()[-1] 
        else:
            card_index = paragraphs[1]

        match = re.search(r"(\d+)", card_index)
        if match:
            try:
                action_index = int(match.group(1))
                if 0 <= action_index < max_index:
                    return action_index
            except ValueError:
                pass
        return None
    
    def _make_api_call(self, prompt: str) -> Optional[dict]:
        try:
            start = time.time()

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}]

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )

            elapsed = time.time() - start
            self.stats.total_requests += 1
            self.stats.response_times.append(elapsed)

            response_dict = response.model_dump()

            if response.usage:
                self.stats.total_tokens += response.usage.total_tokens

            return response_dict

        except Exception as e:
            print(f"Api call failed: {e}")
            self.stats.invalid_responses += 1
            return None

    def choose_card(self, game_state: GameState, battle_state: BattleState) -> PlayCard | EndAgentTurn:
        options = self.get_choose_card_options(game_state, battle_state)

        prompt_parts = []
        
        prompt_parts.append(self._build_request(len(options)))

        prompt_parts.append(self._build_game_state(game_state, battle_state, options))
        prompt_parts.append(self._build_game_context(game_state, battle_state))

        prompt = "\n".join(prompt_parts)

        for _ in range(self.config.retry_limit):
            response = self._make_api_call(prompt)

            if response is None:
                time.sleep(1)
                continue

            content = response['choices'][0]['message']['content'].strip()
            move_index = self._parse_response(content, len(options))

            if move_index is not None:
                return options[move_index]

            self.stats.invalid_responses += 1

        playable = [opt for opt in options if isinstance(opt, PlayCard)]
        return random.choice(playable) if playable else options[-1]

    def choose_agent_target(self, battle_state: BattleState, list_name: str,
                          agent_list: list[Agent]) -> Agent:
        if len(agent_list) == 1:
            return agent_list[0]
        return min(agent_list, key=lambda a: a.health)

    def choose_card_target(self, battle_state: BattleState, list_name: str,
                          card_list: list[Card]) -> Card:
        if len(card_list) == 1:
            return card_list[0]
        return card_list[0]

    def get_statistics(self) -> dict:
        return {
            'total_requests': self.stats.total_requests,
            'invalid_responses': self.stats.invalid_responses,
            'invalid_rate': self.stats.invalid_rate,
            'total_tokens': self.stats.total_tokens,
            'avg_response_time': self.stats.avg_response_time
        }
