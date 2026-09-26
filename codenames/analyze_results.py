"""
Analyze experiment results and produce strategy comparison tables + charts.

Usage:
    python analyze_results.py                # console summary + markdown report
    python analyze_results.py --charts       # also generate PNG charts (requires matplotlib)
"""

import json
import os
import argparse
from collections import defaultdict

RESULTS_FILE = os.path.join("results", "experiment_results.json")
REPORT_FILE = os.path.join("results", "analysis_report.md")
STRATEGIES = ["Default", "Cautious", "Risky", "COT", "Self Refine", "Solo Performance"]


def load_results():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # filter out error entries
    valid = {k: v for k, v in data.items() if "did_win" in v}
    errors = {k: v for k, v in data.items() if "error" in v}
    return valid, errors


def compute_stats(results):
    """Group results by provider and strategy combo, compute metrics."""
    by_provider = defaultdict(list)
    for r in results.values():
        by_provider[r["provider"]].append(r)

    stats = {}
    for provider, games in by_provider.items():
        combo_stats = {}
        for game in games:
            key = (game["cm_strategy"], game["g_strategy"])
            combo_stats.setdefault(key, []).append(game)

        provider_stats = {}
        for (cm, g), game_list in combo_stats.items():
            total = len(game_list)
            wins = sum(1 for x in game_list if x["did_win"])
            assassins = sum(x.get("assassin", 0) for x in game_list)
            avg_time = sum(x.get("time_s", 0) for x in game_list) / total
            avg_red = sum(x.get("red", 0) for x in game_list) / total
            provider_stats[(cm, g)] = {
                "games": total,
                "wins": wins,
                "win_rate": wins / total if total > 0 else 0,
                "assassin_hits": assassins,
                "assassin_rate": assassins / total if total > 0 else 0,
                "avg_time_s": round(avg_time, 1),
                "avg_red_found": round(avg_red, 1),
            }
        stats[provider] = provider_stats

    return stats


def print_summary(stats, errors):
    """Print a formatted summary to console."""
    print("=" * 70)
    print("CODENAMES AI EXPERIMENT ANALYSIS")
    print("=" * 70)

    total_games = sum(len(ps) for ps in stats.values() for ps in [ps])
    print(f"\nTotal valid games: {sum(s['games'] for ps in stats.values() for s in ps.values())}")
    print(f"Error entries: {len(errors)}")

    for provider, provider_stats in stats.items():
        print(f"\n{'=' * 70}")
        print(f"PROVIDER: {provider.upper()}")
        print(f"{'=' * 70}")

        all_games = sum(s["games"] for s in provider_stats.values())
        all_wins = sum(s["wins"] for s in provider_stats.values())
        all_assassins = sum(s["assassin_hits"] for s in provider_stats.values())
        print(f"Total: {all_wins}/{all_games} wins ({100 * all_wins / all_games:.1f}%) | {all_assassins} assassin hits")

        # strategy combo table
        header = f"  {'CM Strategy':<18} {'G Strategy':<18} {'Games':>5} {'Wins':>5} {'Win%':>6} {'Assn':>5} {'AvgTime':>8} {'AvgRed':>7}"
        print(f"\n{header}")
        print("  " + "-" * (len(header) - 2))

        for (cm, g) in sorted(provider_stats.keys()):
            s = provider_stats[(cm, g)]
            print(f"  {cm:<18} {g:<18} {s['games']:>5} {s['wins']:>5} {100*s['win_rate']:>5.1f}% {s['assassin_hits']:>5} {s['avg_time_s']:>7.1f}s {s['avg_red_found']:>6.1f}")

        # marginal analysis: best CM strategy (across all guessers)
        print(f"\n  --- Codemaster Marginal (across all guesser strategies) ---")
        cm_marginal = defaultdict(lambda: {"games": 0, "wins": 0, "assassins": 0})
        for (cm, g), s in provider_stats.items():
            cm_marginal[cm]["games"] += s["games"]
            cm_marginal[cm]["wins"] += s["wins"]
            cm_marginal[cm]["assassins"] += s["assassin_hits"]

        for cm in STRATEGIES:
            if cm in cm_marginal:
                m = cm_marginal[cm]
                wr = 100 * m["wins"] / m["games"] if m["games"] > 0 else 0
                print(f"  {cm:<20} {m['wins']:>3}/{m['games']:<3} wins ({wr:>5.1f}%) | {m['assassins']} assassin hits")

        # marginal analysis: best G strategy
        print(f"\n  --- Guesser Marginal (across all codemaster strategies) ---")
        g_marginal = defaultdict(lambda: {"games": 0, "wins": 0, "assassins": 0})
        for (cm, g), s in provider_stats.items():
            g_marginal[g]["games"] += s["games"]
            g_marginal[g]["wins"] += s["wins"]
            g_marginal[g]["assassins"] += s["assassin_hits"]

        for g in STRATEGIES:
            if g in g_marginal:
                m = g_marginal[g]
                wr = 100 * m["wins"] / m["games"] if m["games"] > 0 else 0
                print(f"  {g:<20} {m['wins']:>3}/{m['games']:<3} wins ({wr:>5.1f}%) | {m['assassins']} assassin hits")


def generate_report(stats, errors):
    """Generate a markdown report."""
    lines = []
    lines.append("# Codenames AI Experiment Analysis Report\n")

    total_valid = sum(s["games"] for ps in stats.values() for s in ps.values())
    lines.append(f"**Total valid games:** {total_valid}  ")
    lines.append(f"**Error entries:** {len(errors)}\n")

    for provider, provider_stats in stats.items():
        lines.append(f"## {provider.upper()}\n")

        all_games = sum(s["games"] for s in provider_stats.values())
        all_wins = sum(s["wins"] for s in provider_stats.values())
        all_assassins = sum(s["assassin_hits"] for s in provider_stats.values())
        lines.append(f"**Overall:** {all_wins}/{all_games} wins ({100 * all_wins / all_games:.1f}%) | {all_assassins} assassin hits\n")

        # combo table
        lines.append("### Strategy Combo Results\n")
        lines.append("| CM Strategy | G Strategy | Games | Wins | Win% | Assassin Hits | Avg Time (s) | Avg Red Found |")
        lines.append("|-------------|------------|------:|-----:|-----:|--------------:|-------------:|--------------:|")
        for (cm, g) in sorted(provider_stats.keys()):
            s = provider_stats[(cm, g)]
            lines.append(f"| {cm} | {g} | {s['games']} | {s['wins']} | {100*s['win_rate']:.1f}% | {s['assassin_hits']} | {s['avg_time_s']} | {s['avg_red_found']} |")

        # marginals
        lines.append("\n### Codemaster Marginal Performance\n")
        lines.append("| CM Strategy | Games | Wins | Win% | Assassin Hits |")
        lines.append("|-------------|------:|-----:|-----:|--------------:|")
        cm_marginal = defaultdict(lambda: {"games": 0, "wins": 0, "assassins": 0})
        for (cm, g), s in provider_stats.items():
            cm_marginal[cm]["games"] += s["games"]
            cm_marginal[cm]["wins"] += s["wins"]
            cm_marginal[cm]["assassins"] += s["assassin_hits"]
        for cm in STRATEGIES:
            if cm in cm_marginal:
                m = cm_marginal[cm]
                wr = 100 * m["wins"] / m["games"] if m["games"] > 0 else 0
                lines.append(f"| {cm} | {m['games']} | {m['wins']} | {wr:.1f}% | {m['assassins']} |")

        lines.append("\n### Guesser Marginal Performance\n")
        lines.append("| G Strategy | Games | Wins | Win% | Assassin Hits |")
        lines.append("|------------|------:|-----:|-----:|--------------:|")
        g_marginal = defaultdict(lambda: {"games": 0, "wins": 0, "assassins": 0})
        for (cm, g), s in provider_stats.items():
            g_marginal[g]["games"] += s["games"]
            g_marginal[g]["wins"] += s["wins"]
            g_marginal[g]["assassins"] += s["assassin_hits"]
        for g in STRATEGIES:
            if g in g_marginal:
                m = g_marginal[g]
                wr = 100 * m["wins"] / m["games"] if m["games"] > 0 else 0
                lines.append(f"| {g} | {m['games']} | {m['wins']} | {wr:.1f}% | {m['assassins']} |")

        lines.append("")

    return "\n".join(lines)


def generate_charts(stats):
    """Generate heatmap charts for win rate and assassin rate."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use("Agg")
    except ImportError:
        print("matplotlib not installed, skipping charts. Install with: pip install matplotlib")
        return

    os.makedirs("results", exist_ok=True)

    for provider, provider_stats in stats.items():
        # Build 6x6 grids
        cm_strategies = [s for s in STRATEGIES if any(k[0] == s for k in provider_stats)]
        g_strategies = [s for s in STRATEGIES if any(k[1] == s for k in provider_stats)]

        if not cm_strategies or not g_strategies:
            continue

        # Win rate heatmap
        win_grid = []
        for cm in cm_strategies:
            row = []
            for g in g_strategies:
                s = provider_stats.get((cm, g))
                row.append(100 * s["win_rate"] if s else float("nan"))
            win_grid.append(row)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

        im1 = ax1.imshow(win_grid, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
        ax1.set_xticks(range(len(g_strategies)))
        ax1.set_xticklabels(g_strategies, rotation=45, ha="right", fontsize=9)
        ax1.set_yticks(range(len(cm_strategies)))
        ax1.set_yticklabels(cm_strategies, fontsize=9)
        ax1.set_xlabel("Guesser Strategy")
        ax1.set_ylabel("Codemaster Strategy")
        ax1.set_title(f"Win Rate % — {provider.upper()}")
        for i in range(len(cm_strategies)):
            for j in range(len(g_strategies)):
                val = win_grid[i][j]
                if val == val:  # not NaN
                    s = provider_stats.get((cm_strategies[i], g_strategies[j]))
                    ax1.text(j, i, f"{val:.0f}%\n({s['games']}g)", ha="center", va="center", fontsize=8)
        plt.colorbar(im1, ax=ax1, shrink=0.8)

        # Assassin rate heatmap
        assn_grid = []
        for cm in cm_strategies:
            row = []
            for g in g_strategies:
                s = provider_stats.get((cm, g))
                row.append(100 * s["assassin_rate"] if s else float("nan"))
            assn_grid.append(row)

        im2 = ax2.imshow(assn_grid, cmap="YlOrRd", vmin=0, vmax=100, aspect="auto")
        ax2.set_xticks(range(len(g_strategies)))
        ax2.set_xticklabels(g_strategies, rotation=45, ha="right", fontsize=9)
        ax2.set_yticks(range(len(cm_strategies)))
        ax2.set_yticklabels(cm_strategies, fontsize=9)
        ax2.set_xlabel("Guesser Strategy")
        ax2.set_ylabel("Codemaster Strategy")
        ax2.set_title(f"Assassin Hit Rate % — {provider.upper()}")
        for i in range(len(cm_strategies)):
            for j in range(len(g_strategies)):
                val = assn_grid[i][j]
                if val == val:  # not NaN
                    ax2.text(j, i, f"{val:.0f}%", ha="center", va="center", fontsize=8)
        plt.colorbar(im2, ax=ax2, shrink=0.8)

        plt.tight_layout()
        chart_path = os.path.join("results", f"analysis_{provider}.png")
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Chart saved: {chart_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Codenames experiment results")
    parser.add_argument("--charts", action="store_true", help="Generate PNG charts (requires matplotlib)")
    args = parser.parse_args()

    valid, errors = load_results()
    stats = compute_stats(valid)

    print_summary(stats, errors)

    if args.charts:
        generate_charts(stats)

    report_md = generate_report(stats, errors)
    os.makedirs("results", exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"\nMarkdown report saved: {REPORT_FILE}")


if __name__ == "__main__":
    main()
