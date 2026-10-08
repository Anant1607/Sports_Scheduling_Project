import pulp
import time

def run_exact_solver(prob):
    print("Initializing HiGHS exact solver...")
    
    # Disabling heuristics in solver
    heuristic_flags = [
        "mip_heuristic_run_feasibility_jump=False",
        "mip_heuristic_run_rins=False",
        "mip_heuristic_run_rens=False",
        "mip_heuristic_run_root_reduced_cost=False",
        "mip_heuristic_run_zi_round=False",
        "mip_heuristic_run_shifting=False"
    ]
    
    # Initialize the HiGHS solver with logging enabled and our exactness flags applied
    solver = pulp.getSolver('HiGHS', msg=True, options=heuristic_flags)
    
    print("Executing branch-and-cut search...")
    start_time = time.time()
    
    # Run the optimization
    prob.solve(solver)
    
    solve_time = time.time() - start_time
    status_string = pulp.LpStatus[prob.status]
    
    # Extract the objective value only if a mathematically valid schedule was found
    if prob.status == pulp.LpStatusOptimal:
        objective_value = pulp.value(prob.objective)
        print(f"Optimal schedule found!")
    elif prob.status == pulp.LpStatusInfeasible:
        objective_value = None
        print(f"CRITICAL: Model is Infeasible. The constraints logically contradict each other.")
    else:
        objective_value = None
        print(f"Solver halted with status: {status_string}")
        
    # Performance Measurement Logs
    print("-" * 30)
    print(f"Final Status   : {status_string}")
    print(f"Solve Time     : {solve_time:.4f} seconds")
    if objective_value is not None:
        print(f"Objective Value: {objective_value}")
    print("-" * 30)
        
    # Return the data to the main execution script
    return status_string, solve_time, objective_value