import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Read the CSV file
results = pd.read_csv('evaluation_results/evaluation_results/experiment1/1764559415_suite_starter_deck_starter-ironclad_enemies_g_50_boteval/results.csv')

# Get unique bot names
bots = results['BotName'].unique()

# Create figure with subplots
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
fig.suptitle('Evaluation Results', fontsize=16)

# Win Rate by Bot
ax1 = axes[0]
win_rates = results.groupby('BotName')['Win'].mean() * 100
win_rates.plot(kind='bar', ax=ax1, color='steelblue', alpha=0.7)
ax1.set_title('Win Rate by Bot')
ax1.set_ylabel('Win Rate (%)')
ax1.set_xlabel('Bot Name')
ax1.tick_params(axis='x', rotation=45)
ax1.grid(axis='y', alpha=0.3)

# Player Health Distribution (wins only)
ax2 = axes[1]
wins = results[results['Win'] == True]
colors = plt.cm.tab10(np.linspace(0, 1, len(bots)))

for idx, bot in enumerate(bots):
    bot_data = wins[wins['BotName'] == bot]['PlayerHealth']
    if len(bot_data) > 0:
        ax2.hist(bot_data, alpha=0.5, label=bot, bins=15, color=colors[idx])
        # Add vertical dashed line for mean
        mean_health = bot_data.mean()
        ax2.axvline(mean_health, linestyle='--', linewidth=2, color=colors[idx])

ax2.set_title('Player Health Distribution (Wins Only)')
ax2.set_xlabel('Player Health')
ax2.set_ylabel('Frequency')
ax2.legend(loc='upper left', fontsize=8)
ax2.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('evaluation_comparison_first_vs_second.png', dpi=300, bbox_inches='tight')
print("Histogram saved as 'evaluation_comparison_first_vs_second.png'")

# Print summary statistics
print("\n=== EVALUATION SUMMARY ===")
print(f"Total games: {len(results)}")
for bot in bots:
    bot_data = results[results['BotName'] == bot]
    wins = bot_data['Win'].sum()
    total = len(bot_data)
    win_rate = (wins / total * 100) if total > 0 else 0
    avg_health = bot_data[bot_data['Win'] == True]['PlayerHealth'].mean() if wins > 0 else 0
    print(f"{bot}: {wins}/{total} wins ({win_rate:.1f}%), Avg health on win: {avg_health:.1f}")

plt.show()
