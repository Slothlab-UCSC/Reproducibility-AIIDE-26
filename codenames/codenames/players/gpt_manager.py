import os
import concurrent.futures
from openai import OpenAI
import time
from openai import RateLimitError
import random
from google import genai
import anthropic


game_rules = """
Codenames is a word-based game of language understanding and communication.
Players are split into two teams (red and blue), with each team consisting of a Codemaster and Guesser.
Setup:
At the start of the game, the board consists of 25 English words.
The Codemasters on each team has access to a hidden map that tells them the identity of all of the words (Red, Blue, Civilian or Assassin).
The Guessers on each team do not have access to this map, and so do not know the identity of any words.
Players need to work as a team to select their words as quickly as possible, while minimizing the number of incorrect guesses.
Turns:
At the start of each team's turn, the Codemaster supplies a clue and a number (the number of words related to that clue).
The clue must:
- Be semantically related to the words the Codemaster wants their Guesser to guess.
- Be a single English word.
- NOT be derived from or derive one of the words on the board.
The Guesser then selects from the remaining words on he board, based on the which words are most associated with the Codemaster's clue.
The identity of the selected word is then revealed to all players.
If the Guesser selected a word that is their team's colour, then they may get to pick another word.
The Guesser must always make at least one guess each turn, and can guess up to one word more than the number provided in the Codemaster's clue.
If a Guesser selects a word that is not their team's colour, their turn ends.
The Guesser can choose to stop selecting words (ending their turn) any time after the first guess.
Ending:
Play proceeds, passing back and forth, until one of three outcomes is achieved:
All of the words of your team's colour have been selected -- you win
All of the words of the other team's colour have been selected -- you lose
You select the assassin tile -- you lose

"""
class GPT:
    def __init__(self, system_prompt, version, provider=None):
        super().__init__()

        # "openai" or "gemini"
        self.provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
        self.model_version = version

        if self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY env var is not set")
            self.client = OpenAI(api_key=api_key)

        elif self.provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY env var is not set")
            self.client = genai.Client(api_key=api_key)

        elif self.provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY env var is not set")
            self.client = anthropic.Anthropic(api_key=api_key)

        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

        # system prompt stored separately for Anthropic (not in messages array)
        self.system_prompt = system_prompt
        self.conversation_history = [{"role": "system", "content": system_prompt}]
        self.interaction_log = []

    def _mock_reply(self, prompt: str) -> str:
        text = prompt.lower()
        if "codemaster" in text or "clue" in text:
            return "('animal',2)"
        if "guess" in text:
            return "DOG, CAT"
        return "SAFE"

    def reset_history(self):
        """Keep only the system prompt, discard prior turns to reduce token usage."""
        self.conversation_history = [self.conversation_history[0]]

    def clear_interaction_log(self):
        """Clear the interaction log between games."""
        self.interaction_log = []

    def _log_interaction(self, prompt: str, response: str):
        self.interaction_log.append({
            "timestamp": time.time(),
            "provider": self.provider,
            "model": self.model_version,
            "prompt": prompt,
            "response": response,
        })

    def talk_to_ai(self, prompt: str, max_retries: int = 5, max_tokens: int = 100, json_mode: bool = False) -> str:
        """
        Send a message to the model, with:
        - optional mock mode (MOCK_GPT=1)
        - retry on RateLimitError for OpenAI
        - json_mode=True: request structured JSON output (prompt must mention "JSON")
        """
        # Add user message
        self.conversation_history.append({"role": "user", "content": prompt})

        # Mock mode for debugging / no-API runs
        if os.getenv("MOCK_GPT") == "1":
            response = self._mock_reply(prompt)
            self.conversation_history.append(
                {"role": "assistant", "content": response}
            )
            self._log_interaction(prompt, response)
            return response

        # ---------- OpenAI path ----------
        if self.provider == "openai":
            kwargs = {
                "messages": self.conversation_history,
                "model": self.model_version,
                "max_tokens": max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            for attempt in range(max_retries):
                try:
                    completion = self.client.chat.completions.create(**kwargs)
                    response = completion.choices[0].message.content
                    self.conversation_history.append(
                        {"role": "assistant", "content": response}
                    )
                    self._log_interaction(prompt, response)
                    return response

                except (RateLimitError, Exception) as e:
                    if attempt == max_retries - 1:
                        raise
                    # Retry on RateLimit, Timeout, and transient API errors
                    wait_time = min((2 ** attempt) + random.random(), 30)
                    print(
                        f"[OpenAI error] {type(e).__name__}: {e}. "
                        f"Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(wait_time)

        # ---------- Gemini path ----------
        if self.provider == "gemini":
            history_text = ""
            for msg in self.conversation_history:
                role = msg["role"].upper()
                content = msg["content"]
                history_text += f"{role}: {content}\n"
            history_text += "ASSISTANT:"

            config = {"max_output_tokens": max_tokens}
            if json_mode:
                config["response_mime_type"] = "application/json"

            for attempt in range(max_retries):
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                        _fut = _ex.submit(
                            self.client.models.generate_content,
                            model=self.model_version,
                            contents=history_text,
                            config=config,
                        )
                        try:
                            resp = _fut.result(timeout=60)
                        except concurrent.futures.TimeoutError:
                            raise RuntimeError("Gemini API call timed out after 60s")
                    response = resp.text
                    self.conversation_history.append(
                        {"role": "assistant", "content": response}
                    )
                    self._log_interaction(prompt, response)
                    return response
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait_time = min((2 ** attempt) + random.random(), 30)
                    print(f"[Gemini error] {e}. Retrying in {wait_time:.1f}s (attempt {attempt+1}/{max_retries})...")
                    time.sleep(wait_time)

        # ---------- Anthropic path ----------
        if self.provider == "anthropic":
            # Anthropic takes system separately; messages must be user/assistant only
            messages = [m for m in self.conversation_history if m["role"] != "system"]
            kwargs = {
                "model": self.model_version,
                "max_tokens": max_tokens,
                "system": self.system_prompt,
                "messages": messages,
            }
            response_obj = self.client.messages.create(**kwargs)
            response = response_obj.content[0].text
            self.conversation_history.append({"role": "assistant", "content": response})
            self._log_interaction(prompt, response)
            return response

        raise RuntimeError(f"Unsupported provider: {self.provider}")


