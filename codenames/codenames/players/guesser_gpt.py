import os
import random
import json
from codenames.players.gpt_manager import game_rules, GPT
from codenames.players.guesser import Guesser


class AIGuesser(Guesser):
    """
    Guesser that uses GPT.
    Now supports the SAME strategy names as the Codemaster:
    - "Default"
    - "Cautious"
    - "Risky"
    - "COT"  (chain-of-thought, 2-step)
    - "Self Refine"
    - "Solo Performance"
    """


    def __init__(self, team: str = "Red", strategy: str = "Default"):
        super().__init__()
        self.team = team
        self.strategy = strategy
        self.num = 0
        self.guesses = 0

        system_prompt = (
            game_rules
            + f"You are playing the game Codenames as the {team} Guesser. "
            + "Never reveal hidden roles. Only return guesses when asked. "
        )

        # Decide provider + model
        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        if provider == "gemini":
            model = "gemini-2.5-flash-lite"
        elif provider == "anthropic":
            model = "claude-haiku-4-5"
        else:
            model = "gpt-4o-mini"

        self.manager = GPT(
            system_prompt=system_prompt,
            version=model,
            provider=provider,
        )


    # ---------------- basic setup ----------------

    def set_board(self, words):
        # board words can have * markers, we will filter them later
        self.words = words

    def set_clue(self, clue, num):
        self.clue = clue
        self.num = int(num)
        self.guesses = 0
        # we keep the strategy from __init__, but you could also pass it per-turn here
        print("The clue is:", clue, num)
        return [clue, num]

    # ---------------- helpers ----------------

    def get_remaining_options(self):
        remaining_options = []
        for w in self.words:
            # skip already revealed ones
            if len(w) > 0 and w[0] == "*":
                continue
            remaining_options.append(w)
        return remaining_options

    # ---------------- keep guessing? ----------------

    def keep_guessing(self):
        """
        Different prompt-engineering styles for deciding whether to keep guessing.
        """
        label = str(getattr(self, "strategy", "Default")).strip().lower()

        # hard stop for cautious: guess at most 1 word per turn
        if label == "cautious":
            return self.guesses < 1

        # risky: try to use up to num + 1 guesses, no GPT needed
        if label == "risky":
            max_allowed = (self.num or 0) + 1
            return self.guesses < max_allowed

        # other strategies → ask the model, but with slightly different instructions
        invalid_timer = 0
        response = None
        self.manager.reset_history()

        while response is None and self.guesses < self.num:
            base = (
                "The remaining words are: " + str(self.get_remaining_options()) + ". "
                + f"The Codemaster's clue is: ({self.clue}, {self.num}). "
                + f"You have already picked {self.guesses} words this turn. "
            )

            if label == "cot":
                prompt = (
                    base
                    + "Think step by step whether there are still high-confidence targets left. "
                    + "Then answer ONLY 'yes' or 'no'."
                )
            elif label in {"self refine", "self-refine", "self_refine"}:
                prompt = (
                    base
                    + "Decide if there is another SAFE guess that is very likely to be your team's word. "
                    + "If you are unsure, answer 'no'. Answer ONLY 'yes' or 'no'."
                )
            elif label in {"solo performance", "solo-performance", "solo_performance"}:
                prompt = (
                    base
                    + "First internally evaluate remaining options, but output ONLY 'yes' or 'no'. "
                    + "Say 'yes' if there is at least one strong candidate."
                )
            elif label in {"three step", "three-step", "threestep"}:
                prompt = (
                    base
                    + "Think step by step: are there remaining words with high confidence AND low risk "
                    + "of being a non-Red word? Answer ONLY 'yes' or 'no'."
                )
            else:  # default (same as your old code)
                prompt = (
                    base
                    + "Would you like to keep guessing? Answer only 'yes' or 'no'. "
                )

            response = self.manager.talk_to_ai(prompt)
            if isinstance(response, str) and "yes" in response.lower():
                return True
            if isinstance(response, str) and "no" in response.lower():
                return False

            invalid_timer += 1
            if invalid_timer > 10:
                return False
            response = None  # loop again

        return False

    # ---------------- guess a word ----------------

    def get_answer(self):
        """
        Different prompt-engineering styles for choosing the next word.
        """
        label = str(getattr(self, "strategy", "Default")).strip().lower()
        invalid_timer = 0
        guess = None

        while guess is None:
            # Reset history on every attempt so retries don't compound token cost
            self.manager.reset_history()
            remaining = self.get_remaining_options()

            # ---------- DEFAULT ----------
            if label == "default":
                prompt = (
                    "The remaining words are: " + str(remaining) + ". "
                    + f"The Codemaster's clue is: ({self.clue}, {self.num}). "
                    + "Select ONE of the remaining words that is MOST associated with this clue. "
                    + "Return ONLY the word, no extra text."
                )

                response = self.manager.talk_to_ai(prompt)

            # ---------- CAUTIOUS ----------
            elif label == "cautious":
                prompt = (
                    "You must be careful and avoid wrong picks. "
                    "The remaining words are: " + str(remaining) + ". "
                    + f"The Codemaster's clue is: ({self.clue}, {self.num}). "
                    + "Pick the SINGLE safest word (the one that is clearly linked). "
                    + "If multiple words are possible, pick the one with the strongest and most obvious link. "
                    + "Return ONLY the word."
                )
                response = self.manager.talk_to_ai(prompt)

            # ---------- RISKY ----------
            elif label == "risky":
                prompt = (
                    "You can be aggressive. "
                    "The remaining words are: " + str(remaining) + ". "
                    + f"The Codemaster's clue is: ({self.clue}, {self.num}). "
                    + "Pick the word that is MOST LIKELY intended, even if there is a bit of risk. "
                    + "Return ONLY the word."
                )
                response = self.manager.talk_to_ai(prompt)

            # ---------- CHAIN OF THOUGHT ----------
            elif label == "cot":
                # step 1: reason
                reasoning_prompt = (
                    "We are playing Codenames.\n"
                    f"Clue: ({self.clue}, {self.num}).\n"
                    f"Remaining words: {remaining}.\n"
                    "Think step by step about which remaining word best matches the clue. "
                    "List the top 3 candidates and score them 0–1.\n"
                    "Do NOT output the final guess yet."
                )
                _ = self.manager.talk_to_ai(reasoning_prompt, max_tokens=150)

                # step 2: final
                prompt = (
                    f"Now give me ONLY the single final guess word for the clue ({self.clue}, {self.num}) "
                    f"from this list: {remaining}. Return ONLY the word."
                )
                response = self.manager.talk_to_ai(prompt)

            # ---------- SELF REFINE ----------
            elif label in {"self refine", "self-refine", "self_refine"}:
                # initial raw guess
                initial_prompt = (
                    "The remaining words are: " + str(remaining) + ". "
                    + f"The Codemaster's clue is: ({self.clue}, {self.num}). "
                    + "Pick the most likely word. Return ONLY the word."
                )
                initial_guess = self.manager.talk_to_ai(initial_prompt)

                # Critique variant is selectable via SELF_REFINE_CRITIQUE for the
                # critique-ablation study:
                #   buggy      - original negative-framing prompt (reason about hidden roles)
                #   fixed      - positive clue-association reframe (default)
                #   verifiable - critique grounded ONLY in clue<->word association (no hidden
                #                roles): a question the Guesser can actually answer
                #   none       - ablation: no critique step, keep the initial guess
                variant = os.getenv("SELF_REFINE_CRITIQUE", "fixed").lower()
                if variant == "none":
                    response = initial_guess
                else:
                    if variant == "buggy":
                        critique_prompt = (
                            f"You guessed: {initial_guess}. "
                            f"Clue: ({self.clue}, {self.num}). Remaining words: {remaining}. "
                            "Check if this guess could accidentally be Blue/Civilian/Assassin if this were a real board. "
                            "If the guess is risky, suggest a safer one from the remaining words. "
                            "Return ONLY the final safest word."
                        )
                    elif variant == "verifiable":
                        critique_prompt = (
                            f"Your initial guess was: {initial_guess}. "
                            f"Clue: ({self.clue}, {self.num}). Remaining words: {remaining}. "
                            f"Consider ONLY how strongly each remaining word is associated in meaning "
                            f"with the clue word '{self.clue}'. Is there a remaining word whose meaning is "
                            f"MORE strongly associated with '{self.clue}' than your initial guess? "
                            "Judge purely by word association; do NOT try to infer hidden roles. "
                            "If another word is more strongly associated, return it; otherwise keep your "
                            "initial guess. Return ONLY the single word."
                        )
                    else:  # fixed
                        critique_prompt = (
                            f"Your initial guess was: {initial_guess}. "
                            f"Clue: ({self.clue}, {self.num}). Remaining words: {remaining}. "
                            "You are the RED team guesser. Review whether your initial guess is the strongest match for the clue. "
                            "Is there a word in the remaining list with an even clearer semantic connection to the clue? "
                            "Pick the word you are MOST CONFIDENT belongs to the RED team — the one most directly tied to the clue. "
                            "If you are not sure, keep your initial guess rather than switching. "
                            "Return ONLY the single best word from the remaining list."
                        )
                    response = self.manager.talk_to_ai(critique_prompt)

            # ---------- SOLO PERFORMANCE ----------
            elif label in {"solo performance", "solo-performance", "solo_performance"}:
                prompt = (
                    "Act as a strong Codenames guesser. "
                    f"Clue: ({self.clue}, {self.num}). "
                    f"Remaining words: {remaining}. "
                    "Internally do the reasoning, but output ONLY the final chosen word."
                )
                response = self.manager.talk_to_ai(prompt)

            # ---------- THREE STEP ----------
            elif label in {"three step", "three-step", "threestep"}:
                # Step 1: brainstorm candidates with rationale
                step1_prompt = (
                    f"We are playing Codenames. Clue: ({self.clue}, {self.num}).\n"
                    f"Remaining board words: {remaining}.\n"
                    "List ALL words from the board that could relate to this clue. "
                    "For each, briefly explain the semantic connection. Do NOT guess yet."
                )
                _ = self.manager.talk_to_ai(step1_prompt, max_tokens=150)

                # Step 2: score each candidate for risk
                step2_prompt = (
                    "For each candidate above, score the RISK that it is actually a Blue, Civilian, or Assassin word "
                    "rather than a Red word. Score 1 (very safe — clearly Red) to 5 (very risky — could easily be non-Red). "
                    "Format: WORD — risk: N — reason: ..."
                )
                _ = self.manager.talk_to_ai(step2_prompt, max_tokens=150)

                # Step 3: pick the safest highest-confidence word and return JSON
                step3_prompt = (
                    f"Based on the semantic match and risk scores above, pick the single best guess from {remaining}. "
                    "Choose the word with the strongest clue match AND lowest risk of being non-Red. "
                    "Return ONLY a JSON object with key 'guess' (string, must be one of the remaining words exactly as listed). "
                    "Example: {\"guess\": \"MARBLE\"}"
                )
                response = self.manager.talk_to_ai(step3_prompt, max_tokens=50, json_mode=True)

            # ---------- fallback ----------
            else:
                prompt = (
                    "The remaining words are: " + str(remaining) + ". "
                    + f"The Codemaster's clue is: ({self.clue}, {self.num}). "
                    + "Select one of the remaining words that is most associated with this clue. "
                    + "You must select one of the remaining words and provide no additional text."
                )
                response = self.manager.talk_to_ai(prompt)

            # ---------- parse ----------
            if not isinstance(response, str):
                response = str(response)

            # Three Step returns JSON: {"guess": "WORD"}
            if label in {"three step", "three-step", "threestep"}:
                try:
                    data = json.loads(response)
                    candidate = str(data["guess"]).strip().upper()
                except Exception:
                    candidate = response.strip().upper()
            else:
                candidate = response.strip().upper()

            # plain match
            if candidate in self.words:
                guess = candidate
            # first token
            elif candidate.split(" ")[0].strip() in self.words:
                guess = candidate.split(" ")[0].strip()
            # quoted
            elif len(response.split('"')) > 2 and response.split('"')[1].upper() in self.words:
                guess = response.split('"')[1].upper()
            elif len(response.split("'")) > 2 and response.split("'")[1].upper() in self.words:
                guess = response.split("'")[1].upper()
            # too many bad tries → pick random
            elif invalid_timer > 10:
                print("You have made too many invalid guesses, selecting random remaining word")
                guess = random.choice(remaining)
            else:
                print("Warning! Invalid guess from model:", candidate)
                invalid_timer += 1

        self.guesses += 1
        return guess
