import pandas as pd
import argparse
import json
import os
from typing import Optional


def load_exe_times(json_path: Optional[str]) -> dict:
    if json_path and os.path.exists(json_path):
        with open(json_path, 'r') as f:
            return json.load(f)
    return {}


def gen_table(csv_path: str, execution_times_path: Optional[str] = None):


    df = pd.read_csv(csv_path)
    execution_times = load_exe_times(execution_times_path)
    grouped = df.groupby('BotName')
    stats_list = []

    for bot_name, group in grouped:
        has_llm_stats = group['TotalRequests'].sum() > 0

        stats = {
            'BotName': bot_name,
            'Test Count': len(group),
            'Avg PlayerHealth': group['PlayerHealth'].mean(),
            'Std PlayerHealth': group['PlayerHealth'].std(),
            'Win Rate (%)': (group['Win'].sum() / len(group) * 100),
        }

        if has_llm_stats:
            stats.update({
                'Total Requests': group['TotalRequests'].sum(),
                'Total Tokens': group['TotalTokens'].sum(),
                'Avg Response Time (s)': group['AvgResponseTime'].mean(),
                'Invalid Response (%)': group['InvalidRate'].mean(),
            })
        else:
            stats.update({
                'Total Requests': 0,
                'Total Tokens': 0,
                'Avg Response Time (s)': 0.0,
                'Invalid Response (%)': 0.0,
            })
        if bot_name in execution_times:
            stats['Avg Execution Time (s)'] = execution_times[bot_name].get('avg_execution', 0.0)
        else:
            stats['Avg Execution Time (s)'] = 'N/A'

        stats_list.append(stats)

    stats_df = pd.DataFrame(stats_list)

    # Reorder columns for better readability
    column_order = [
        'BotName',
        'Total Requests',
        'Total Tokens',
        'Avg Response Time (s)',
        'Invalid Response (%)',
        'Avg Execution Time (s)'
    ]

    stats_df = stats_df[column_order]

    return stats_df


def main():
    parser = argparse.ArgumentParser(description='Generate statistics table from evaluation results')
    parser.add_argument('csv_file', type=str, help='Path to results.csv file')
    parser.add_argument('execution_times', type=str, help='Path to execution_times.json file')
    args = parser.parse_args()

    stats_df = gen_table(args.csv_file, args.execution_times)

    # Determine markdown output path in same directory as results.csv
    base_dir = os.path.dirname(args.csv_file)
    markdown_path = os.path.join(base_dir, 'stats_table.md')

    # Print to console
    print("\n" + "="*80)
    print("STATISTICS TABLE")
    print("="*80 + "\n")
    print(stats_df.to_markdown(index=False, floatfmt='.2f'))
    print("\n" + "="*80 + "\n")

    # Save to markdown file
    with open(markdown_path, 'w') as f:
        f.write(stats_df.to_markdown(index=False, floatfmt='.2f'))
    print(f"Markdown table saved to: {markdown_path}")

    # Print summary
    print("\nSummary:")
    print(f"  Total bots analyzed: {len(stats_df)}")
    print(f"  Results file: {args.csv_file}")
    print(f"  Execution times: {args.execution_times}")


if __name__ == '__main__':
    main()
