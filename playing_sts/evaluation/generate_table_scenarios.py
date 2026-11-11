import pandas as pd
import argparse
import os


def gen_scenario_table(csv_path: str, data_metric: str = 'playerhealth'):

    df = pd.read_csv(csv_path)
    if 'Scenario' not in df.columns:
        raise ValueError("CSV must contain a 'Scenario' column. Use the consolidated results.csv from all_scenarios/")
    metric_mapping = {
        'playerhealth': ('PlayerHealth', 'mean'),
        'winrate': ('Win', lambda x: (x.sum() / len(x) * 100)),
        'totaltokens': ('TotalTokens', 'sum'),
        'totalrequests': ('TotalRequests', 'sum'),
        'stdplayerhealth': ('PlayerHealth', 'std'),
    }

    if data_metric not in metric_mapping:
        raise ValueError(f"Invalid data metric: {data_metric}. Choose from: {', '.join(metric_mapping.keys())}")

    column_name, agg_func = metric_mapping[data_metric]

   
    grouped = df.groupby(['Scenario', 'BotName'])[column_name].agg(agg_func).reset_index()
    pivot_table = grouped.pivot(index='Scenario', columns='BotName', values=column_name)
    preferred_order = ['RandomBot', 'MCTSAgent', 'Backtrack-Depth3', 'None-gpt41', 'RCoT-gpt41']
    existing_columns = [col for col in preferred_order if col in pivot_table.columns]
    other_columns = [col for col in pivot_table.columns if col not in preferred_order]
    pivot_table = pivot_table[existing_columns + other_columns]

    return pivot_table


def main():
    parser = argparse.ArgumentParser(
        description='Generate scenario comparison table (Table 2 from paper)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_table_scenarios.py results.csv --data playerhealth
  python generate_table_scenarios.py results.csv --data winrate
  python generate_table_scenarios.py results.csv --data totaltokens
"""
    )
    parser.add_argument('csv_file', type=str, help='Path to consolidated results.csv file with Scenario column')
    parser.add_argument('--data', type=str, default='playerhealth',
                       help='Data metric to display (default: playerhealth)')
    args = parser.parse_args()

    try:
        pivot_table = gen_scenario_table(args.csv_file, args.data)
        base_dir = os.path.dirname(args.csv_file)
        metric_name = args.data
        markdown_path = os.path.join(base_dir, f'scenario_table_{metric_name}.md')
        print("\n" + "="*80)
        print(f"SCENARIO COMPARISON TABLE - {args.data.upper()}")
        print("="*80 + "\n")
        print(pivot_table.to_markdown(floatfmt='.2f'))
        print("\n" + "="*80 + "\n")

        # Save to markdown file
        with open(markdown_path, 'w') as f:
            f.write(f"# Scenario Comparison - {args.data.upper()}\n\n")
            f.write(pivot_table.to_markdown(floatfmt='.2f'))
        print(f"Markdown table saved to: {markdown_path}")

        print("\nSummary:")
        print(f"  Data metric: {args.data}")
        print(f"  Scenarios: {len(pivot_table)}")
        print(f"  Bot types: {len(pivot_table.columns)}")
        print(f"  Results file: {args.csv_file}")

    except ValueError as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
