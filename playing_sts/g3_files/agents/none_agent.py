from __future__ import annotations
import time
import random
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass, field

from openai import OpenAI
import os
from ggpa.ggpa import GGPA
from ggpa.prompt2 import PromptOption, get_action_prompt, get_agent_target_prompt, get_card_target_prompt, strip_response
from action.action import EndAgentTurn, PlayCard
from auth import OPENROUTER_API_KEY

if TYPE_CHECKING:
    from game import GameState
    from battle import BattleState
    from agent import Agent
    from card import Card


@dataclass
class NoneConfig:
    model: str = "openai/gpt-4.1"
    temperature: float = 0.0
    max_tokens: int = 100
    retry_limit: int = 3


@dataclass
class NoneStatistics:
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


class NoneAgent(GGPA):
    """
    Agent that uses PromptOption.NONE - minimal prompting with no reasoning required.
    Just asks the LLM to pick an action index without explanation.
    """

    def __init__(self, config: Optional[NoneConfig] = None):
        self.config = config or NoneConfig()

        # Determine short name for agent identification
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
        short_name = model_short_names.get(self.config.model, self.config.model.replace("/", "-").replace(":", "-"))

        super().__init__(f"None-{short_name}")

        # All models use OpenRouter API - lazy initialization for pickling
        self._client = None

        self.stats = NoneStatistics()

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

    def _parse_response(self, content: str, max_index: int) -> Optional[int]:
        """Parse the response using strip_response for PromptOption.NONE"""
        # PromptOption.NONE expects just a number in the response
        stripped = strip_response(content, PromptOption.NONE)

        try:
            value = int(stripped)
            if 0 <= value < max_index:
                return value
        except ValueError:
            pass

        return None

    def _make_api_call(self, prompt: str) -> Optional[dict]:
        try:
            start = time.time()

            messages = [{"role": "user", "content": prompt}]

            # Make API call using OpenAI client
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
            print(f"[none] api call failed: {e}")
            self.stats.invalid_responses += 1
            return None

    def choose_card(self, game_state: GameState, battle_state: BattleState) -> PlayCard | EndAgentTurn:
        options = self.get_choose_card_options(game_state, battle_state)

        # Use the existing get_action_prompt with PromptOption.NONE
        # get_context=True on first turn, False afterwards for efficiency
        get_context = (battle_state.turn == 1)

        prompt = get_action_prompt(
            game_state,
            battle_state,
            options,
            PromptOption.NONE,
            get_context=get_context,
            show_option_results=False
        )

        for attempt in range(self.config.retry_limit):
            response = self._make_api_call(prompt)

            if response is None:
                time.sleep(1)
                continue

            content = response['choices'][0]['message']['content'].strip()
            move_index = self._parse_response(content, len(options))

            if move_index is not None:
                return options[move_index]

            self.stats.invalid_responses += 1

        # Fallback: choose random playable card or end turn
        playable = [opt for opt in options if isinstance(opt, PlayCard)]
        return random.choice(playable) if playable else options[-1]

    def choose_agent_target(self, battle_state: BattleState, list_name: str,
                          agent_list: list[Agent]) -> Agent:
        if len(agent_list) == 1:
            return agent_list[0]

        # Use simple heuristic: target enemy with lowest health
        return min(agent_list, key=lambda a: a.health)

    def choose_card_target(self, battle_state: BattleState, list_name: str,
                          card_list: list[Card]) -> Card:
        if len(card_list) == 1:
            return card_list[0]

        # Use simple heuristic: choose first card
        return card_list[0]

    def get_statistics(self) -> dict:
        return {
            'total_requests': self.stats.total_requests,
            'invalid_responses': self.stats.invalid_responses,
            'invalid_rate': self.stats.invalid_rate,
            'total_tokens': self.stats.total_tokens,
            'avg_response_time': self.stats.avg_response_time
        }
