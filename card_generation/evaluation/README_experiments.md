# MiniSTS Automated Evaluation Harness

## Quickstart: Run Experiments

1. **Prepare your deck file**
   - Example: `evaluation/sample_deck.json`
   - Format: JSON array of card names (must match names in CardRepo)
   ```json
   [
     "Strike",
     "Defend",
     "IvanCard"
   ]
   ```

2. **Run the experiment script**
   ```zsh
   python3 evaluation/run_experiments.py --deck evaluation/sample_deck.json --bot random --enemies j --runs 100 --output results.csv
   ```
   - `--deck`: Path to deck file (JSON)
   - `--bot`: Bot type (`random`, `bt3`, `bts5`, `gpt-4-none`, etc.)
   - `--enemies`: Enemy string (`j` = JawWorm, `g` = Goblin, `h` = HobGoblin, `l` = Leech)
   - `--runs`: Number of games to simulate
   - `--output`: Output CSV file
   - `--threads`: Number of parallel jobs (default 4)

3. **Analyze results**
   - Output CSV contains: run, bot, hp, win
   - Use pandas, Excel, or plot scripts to analyze win rates, HP, etc.

## Advanced Usage
- Use any deck file listing valid card names.
- Test with different bots and enemy setups.
- Increase `--runs` and `--threads` for large-scale experiments.

## Troubleshooting
- If a card name is not found, check spelling and CardRepo.
- For custom cards, ensure they are registered in CardRepo.
- For more metrics, extend `run_experiments.py` as needed.

---
Role 3: Game Master (Simulation & Evaluation)
- This harness lets you run hundreds/thousands of games with any deck and agent.
- Collect win rates and other metrics to evaluate card balance.
