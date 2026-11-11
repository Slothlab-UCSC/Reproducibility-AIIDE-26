import csv
import os

# Define the scenario mappings
scenarios = [
    ("bomb_basics-bomb_enemies_h_25_boteval", "Bomb"),
    ("batter_stim_basics-batter-stimulate_enemies_h_25_boteval", "Batter Stim"),
    ("suffer_basics-suffer_enemies_h_25_boteval", "Suffer"),
    ("tolerate_1s3d-tolerate_enemies_h_25_boteval", "Tolerate"),
    ("generated_gigl-random-deck_enemies_h_25_boteval", "GIGL Random")
]

# Base path
base_path = r"C:\Users\jperr\Documents\GitHub\STS-Personal\evaluation_results"
output_file = os.path.join(base_path, "all_scenarios", "results.csv")

# Combined data storage
all_rows = []

# Read each scenario file
for folder_name, scenario_name in scenarios:
    file_path = os.path.join(base_path, folder_name, "results.csv")

    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Add scenario column at the beginning
                row_with_scenario = {"Scenario": scenario_name}
                row_with_scenario.update(row)
                all_rows.append(row_with_scenario)
        print(f"Processed {scenario_name}: {len([r for r in all_rows if r['Scenario'] == scenario_name])} rows")
    else:
        print(f"Warning: File not found - {file_path}")

# Write combined results
if all_rows:
    # Get all fieldnames, ensuring Scenario is first
    fieldnames = ["Scenario"] + [k for k in all_rows[0].keys() if k != "Scenario"]

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nCombined results written to: {output_file}")
    print(f"Total rows: {len(all_rows)}")
else:
    print("No data to write!")
