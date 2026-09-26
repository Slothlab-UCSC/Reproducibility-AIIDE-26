from codenames.players.gpt_manager import game_rules, GPT
from codenames.players.codemaster import Codemaster
import os
import re
import json

class AICodemaster(Codemaster):

    def __init__(self, team: str = "Red", strategy: str = "Default"):
        super().__init__()
        self.team = team
        self.strategy = strategy

        system_prompt = (
            game_rules
            + f"You are playing the game Codenames as the {team} Codemaster. "
            + "Never reveal hidden roles. Only return clues when asked."
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
        self.words = []
        self.maps = []


    
    def set_game_state(self, words, maps):
        """
        words: list[str]     (board words; guessed words often start with '*')
        maps:  list[str]     (same length; one of {'Red','Blue','Civilian','Assassin'})
        """
        self.words = words
        self.maps = maps

    def get_remaining_options(self):
        """Split remaining (unguessed) words by role for prompting."""
        red, blue, civilian, assassin = [], [], [], []
        for i in range(len(self.words)):
            if self.words[i][0] == '*':   # already taken/guessed
                continue
            role = self.maps[i]
            if role == "Red":
                red.append(self.words[i])
            elif role == "Blue":
                blue.append(self.words[i])
            elif role == "Civilian":
                civilian.append(self.words[i])
            elif role == "Assassin":
                assassin.append(self.words[i])
        return red, blue, civilian, assassin
    
    def _build_prompt(self, red, blue, civilian, assassin, extra_msg=""):
        prompt = ""
        prompt += "The remaining words are: "
        prompt += "Red: " + str(red) + ". "
        prompt += "Blue: " + str(blue) + ". "
        prompt += "Civilian: " + str(civilian) + ". "
        prompt += "Assassin: " + str(assassin) + ". "
        prompt += (
            "Provide a single word clue and number for the guesser in the following format "
            "('pebble',2). The clue cannot be derived from or derive one of the words on the board. "
            "Stick to this format exactly and provide no additional text. "
        )
        if extra_msg:
            prompt += extra_msg
        return prompt
    
    def get_clue(self):
        if os.getenv("MOCK_GPT") == "1":
            return "animal", 2

        # Reset conversation history each turn to avoid ballooning token costs
        self.manager.reset_history()

        invalid_timer = 0
        clue = None
        number = None
        red, blue, civilian, assassin = self.get_remaining_options()

        while clue is None or number is None:
            label = str(getattr(self, "strategy", "Default")).strip().lower()

        # ---------- DEFAULT ----------
            if label == "default":
                prompt = "The remaining words are: "
                prompt += "Red: " + str(red) + ". "
                prompt += "Blue: " + str(blue) + ". "
                prompt += "Civilian: " + str(civilian) + ". "
                prompt += "Assassin: " + str(assassin) + ". "
                prompt += "Provide a single word clue and number for the guesser in the following format ('pebble',2). "
                prompt += "Stick to this format exactly and provide no additional text. "
                response = self.manager.talk_to_ai(prompt)

        # ---------- CAUTIOUS ----------
            elif label == "cautious":
                prompt = "The remaining words are: "
                prompt += "Red: " + str(red) + ". "
                prompt += "Blue: " + str(blue) + ". "
                prompt += "Civilian: " + str(civilian) + ". "
                prompt += "Assassin: " + str(assassin) + ". "
                prompt += "Provide a single word clue and number for the guesser in the following format ('pebble',2). "
                prompt += "Stick to this format exactly and provide no additional text. "
                prompt += "Make sure that the number for your guess is always 1. "
                response = self.manager.talk_to_ai(prompt)

        # ---------- RISKY ----------
            elif label == "risky":
                prompt = "The remaining words are: "
                prompt += "Red: " + str(red) + ". "
                prompt += "Blue: " + str(blue) + ". "
                prompt += "Civilian: " + str(civilian) + ". "
                prompt += "Assassin: " + str(assassin) + ". "
                prompt += "Provide a single word clue and number for the guesser in the following format ('pebble',2). "
                prompt += "Stick to this format exactly and provide no additional text. "
                prompt += "Make sure to pick a large number for your guess. "
                response = self.manager.talk_to_ai(prompt)

        # ---------- CHAIN-OF-THOUGHT (two-step) ----------
            elif label == "cot":
                prompt = "The remaining words are: "
                prompt += "Red: " + str(red) + ". "
                prompt += "Blue: " + str(blue) + ". "
                prompt += "Civilian: " + str(civilian) + ". "
                prompt += "Assassin: " + str(assassin) + ". "
                prompt += """
                    Provide a single word clue and number for the guesser in the following format ('pebble' , 2)
                    Solve the task step by step.
                    Your output should be of the following format:
                    ---
                    Steps: Your steps here.
                    Answer: (a single word here) / (A list of words here)
                """
                _ = self.manager.talk_to_ai(prompt, max_tokens=150)  # explanation not parsed; just primes the model
                prompt = "Give me only the final answer in the previous prompt in the following format ('pebble',2). "
                prompt += "Stick to this format exactly and provide no additional text. "
                response = self.manager.talk_to_ai(prompt)

        # ---------- SELF-REFINE ----------
            elif label in {"self refine", "self-refine", "self_refine"}:
                prompt = "The remaining words are: "
                prompt += "Red: " + str(red) + ". "
                prompt += "Blue: " + str(blue) + ". "
                prompt += "Civilian: " + str(civilian) + ". "
                prompt += "Assassin: " + str(assassin) + ". "
                prompt += "Provide a single word clue and number for the guesser in the following format ('pebble',2). "
                prompt += "The clue should avoid associations with Blue, Assassin and Civilian words. "
                initial_response = self.manager.talk_to_ai(prompt)

                # CM_CRITIQUE=off ablates the critique+refine step (keeps initial clue),
                # mirroring the Guesser's SELF_REFINE_CRITIQUE=none for the role x critique 2x2.
                if os.getenv("CM_CRITIQUE", "on").lower() == "off":
                    response = initial_response
                else:
                    other_words = "{" + str(blue).replace("[", "").replace("]", "").replace("'", "") + ", " + \
                                str(assassin).replace("[", "").replace("]", "").replace("'", "") + ", " + \
                                str(civilian).replace("[","").replace("]", "").replace("'", "") + "}"
                    prompt = "Evaluate the Codenames clue " + initial_response + " for the Red words {" + \
                            str(red).replace("[","").replace("]","").replace("'","") + "} and avoid words " + other_words + \
                            " on how related it is to the red words, and likelihood of accidental associate with blue, assassin, or civilian words."
                    prompt += """
                        Give your answer in the form:
                        Feedback:
                        …
                    """
                    feedback = self.manager.talk_to_ai(prompt, max_tokens=150)

                    prompt = "The remaining words are: "
                    prompt += "Red: " + str(red) + ". "
                    prompt += "Blue: " + str(blue) + ". "
                    prompt += "Civilian: " + str(civilian) + ". "
                    prompt += "Assassin: " + str(assassin) + ". "
                    prompt += "Refine the initial Codenames clue '" + initial_response + "' for the above words based on the following feedback: '" + feedback + "'. "
                    prompt += "You can stick with the initial clue if the feedback indicates that this is a good choice. "
                    prompt += "Provide a single word clue and number for the guesser in the following format ('pebble',2). "
                    prompt += "Stick to this format exactly and provide no additional text. "
                    response = self.manager.talk_to_ai(prompt)

            # ---------- SOLO-PERFORMANCE ----------
            elif label in {"solo performance", "solo-performance", "solo_performance"}:
                other_words = "{" + str(blue).replace("[", "").replace("]", "").replace("'", "") + ", " + \
                            str(assassin).replace("[", "").replace("]", "").replace("'", "") + ", " + \
                            str(civilian).replace("[", "").replace("]", "").replace("'", "") +"}"
                prompt = (
                    "You are an expert Codenames Codemaster. "
                    "Simulate an internal discussion between a Linguist and a Strategist to find the best clue, "
                    "then output ONLY the final answer in the format ('pebble',2).\n"
                    "Red words (your team): {" + str(red).replace("[", "").replace("]", "").replace("'", "") + "}. "
                    "Avoid linking to: " + other_words + "."
                )
                initial_response = self.manager.talk_to_ai(prompt, max_tokens=200)
                prompt = "Give me only the final answer in the previous response in the following format ('pebble',2). Stick to this format exactly and provide no additional text. "
                response = self.manager.talk_to_ai(prompt)

            # ---------- THREE STEP ----------
            elif label in {"three step", "three-step", "threestep"}:
                other_words_str = (
                    "Blue: " + str(blue) + ". "
                    + "Civilian: " + str(civilian) + ". "
                    + "Assassin: " + str(assassin) + "."
                )
                # Step 1: brainstorm candidate clues with coverage
                step1_prompt = (
                    "Red words to cover: " + str(red) + ". "
                    + other_words_str + " "
                    "List exactly 5 candidate one-word clues. For each, list which Red words it semantically covers. "
                    "Do NOT give a final answer yet. Format:\n"
                    "1. CLUE — covers: [word1, word2, ...]"
                )
                _ = self.manager.talk_to_ai(step1_prompt, max_tokens=150)

                # Step 2: score each candidate for risk
                step2_prompt = (
                    "For each of the 5 candidates above, score the risk of accidentally leading the guesser "
                    "to a Blue, Civilian, or Assassin word. Score 1 (very safe) to 5 (very risky). "
                    "Consider: " + other_words_str + " "
                    "Format:\n1. CLUE — risk: N — reason: ..."
                )
                _ = self.manager.talk_to_ai(step2_prompt, max_tokens=150)

                # Step 3: pick the best clue (highest coverage, lowest risk) and return JSON
                step3_prompt = (
                    "Based on the coverage and risk scores above, pick the single best clue. "
                    "The clue must not be derived from or derive any word currently on the board: " + str([w for w in self.words if w[0] != '*']) + ". "
                    "Return ONLY a JSON object with keys 'clue' (string) and 'num' (integer). "
                    "Example: {\"clue\": \"animal\", \"num\": 2}"
                )
                response = self.manager.talk_to_ai(step3_prompt, max_tokens=60, json_mode=True)

            # ---------- FALLBACK → DEFAULT ----------
            else:
                prompt = "The remaining words are: "
                prompt += "Red: " + str(red) + ". "
                prompt += "Blue: " + str(blue) + ". "
                prompt += "Civilian: " + str(civilian) + ". "
                prompt += "Assassin: " + str(assassin) + ". "
                prompt += "Provide a single word clue and number for the guesser in the following format ('pebble',2). "
                prompt += "Stick to this format exactly and provide no additional text. "
                response = self.manager.talk_to_ai(prompt)

            # ---------- parse & validate ----------
            try:
                label = str(getattr(self, "strategy", "Default")).strip().lower()
                if label in {"three step", "three-step", "threestep"}:
                    # JSON response: {"clue": "word", "num": 2}
                    data = json.loads(response)
                    clue = re.sub(r'[^A-Z]', '', str(data["clue"]).upper())
                    number = int(data["num"])
                else:
                    split_input = response.upper().strip().split(",")
                    clue = re.sub(r'[^A-Z]', '', split_input[0])
                    number = int(re.sub(r'[^0-9]', '', split_input[1]))
                if number < 1:
                    print("Warning! Invalid clue: " + response + "\nThe clue number must be greater than zero. ")
                    clue = None; number = None; invalid_timer += 1
                else:
                    for i in range(len(self.words)):
                        if self.words[i][0] != '*':
                            if clue in self.words[i] or self.words[i] in clue:
                                print("Warning! Invalid clue: " + response + "\nThe clue cannot be derived from or derive one of the words on the board. ")
                                clue = None; number = None; invalid_timer += 1
                                break
            except Exception:
                print("Warning! Invalid clue: " + response + "\nThat clue format is invalid. ")
                clue = None; number = None; invalid_timer += 1

            if invalid_timer > 10:
                print("You have made too many invalid clues, selecting a default empty clue")
                return ["", 1]

        return [clue, number]

    
    