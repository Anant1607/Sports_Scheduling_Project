import argparse
import os
import sys

import pandas as pd

import extractor
import model
import solver
import validator

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

def main():
    parser = argparse.ArgumentParser(description="Operations Research League Scheduler")
    parser.add_argument("--input", default=os.path.join(PROJECT_ROOT, "input.xlsx"))
    parser.add_argument("--output", default=os.path.join(PROJECT_ROOT, "outputs", "schedule.csv"))
    parser.add_argument("--time-limit", type=float, default=None,
                        help="solver time limit in seconds (default: none)")
    args = parser.parse_args()

    print("Starting Operations Research League Scheduler...\n")

    print("1. Reading input...")
    try:
        df_teams = pd.read_excel(args.input)
        model.validate_input(df_teams)
    except FileNotFoundError:
        print(f"Error: could not find {args.input}. Please ensure the file exists.")
        sys.exit(1)
    except ValueError as err:
        print(f"Error: invalid input. {err}")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    print("2. Building and solving the model...")
    pulp_model, decision_vars = model.build_model(df_teams)
    status, solve_time, obj_val = solver.run_exact_solver(pulp_model, time_limit=args.time_limit)

    if status == "Optimal":
        print(f"\n[+] Optimal schedule found in {solve_time:.4f} seconds.")
        schedule_df = extractor.extract_schedule(decision_vars)

        print("3. Checking the schedule against every rule...")
        problems = validator.validate_schedule(schedule_df, df_teams)
        if problems:
            print(f"[!] The schedule breaks {len(problems)} rule(s). This is a model bug:")
            for line in problems:
                print(f"    - {line}")
        else:
            print("[+] All rule checks passed.")

        if "TeamName" in df_teams.columns:
            names = dict(zip(df_teams["TeamID"], df_teams["TeamName"]))
            schedule_df.insert(2, "Home_Name", schedule_df["Home"].map(names))
            schedule_df.insert(4, "Away_Name", schedule_df["Away"].map(names))

        schedule_df.to_csv(args.output, index=False)
        print(f"[+] Schedule written to {args.output}")

    else:
        if status == "Infeasible":
            print("\n[-] Model is infeasible: the rules cannot all hold together.")
        else:
            print(f"\n[-] No schedule produced. Solver status: {status}")
        print("[-] Writing an empty output file.")
        pd.DataFrame().to_csv(args.output, index=False)
        sys.exit(2)


if __name__ == "__main__":
    main()