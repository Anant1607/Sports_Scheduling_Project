import pandas as pd
import os
import sys

# Tell Python to look inside the src folder for your modules
sys.path.append(os.path.abspath('src'))
import model
import solver
import extractor

def main():
    print("Starting Operations Research League Scheduler...\n")
    
    # Define the exact CSV file paths
    input_file = "data/teams.csv"
    output_file = "outputs/schedule.csv"
    
    print("1. Reading CSV input...")
    try:
        df_teams = pd.read_csv(input_file)
    except FileNotFoundError:
        print(f"Error: Could not find {input_file}. Please ensure the file exists.")
        return

    print("2. Building and solving the model...")
    pulp_model, decision_vars = model.build_model(df_teams)
    status, solve_time, obj_val = solver.run_exact_solver(pulp_model)
    
    os.makedirs('outputs', exist_ok=True)

    if status == 'Optimal':
        print(f"\n[+] Optimal Schedule Found in {solve_time:.4f} seconds!")
        schedule_df = extractor.extract_schedule(decision_vars, dummy_team=None)
        
        # Map team names
        if 'TeamName' in df_teams.columns:
            name_mapping = dict(zip(df_teams['TeamID'], df_teams['TeamName']))
            schedule_df.insert(2, 'Home_Name', schedule_df['Home'].map(name_mapping))
            schedule_df.insert(4, 'Away_Name', schedule_df['Away'].map(name_mapping))
        
        # Save the populated schedule to CSV
        schedule_df.to_csv(output_file, index=False)
        print(f"[+] Success: The optimal schedule has been written to {output_file}")
        
    else:
        print(f"\n[-] Model Infeasible. Solver returned status: {status}")
        print(f"[-] Wiping the output file blank as requested.")
        
        # Create a completely blank DataFrame and overwrite the CSV file with it
        pd.DataFrame().to_csv(output_file, index=False)

if __name__ == "__main__":
    main()