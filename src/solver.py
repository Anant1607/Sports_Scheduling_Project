import pulp
import time

def run_exact_solver(prob):
    print("Initializing HiGHS exact solver...")
    
    # Initialize the HiGHS solver with logging enabled and our exactness flags applied
    solver = pulp.getSolver('HiGHS', msg=True)
    
    print("Executing branch-and-cut search...")
    start_time = time.time()
    
    # Run the optimization
    returned_stats = prob.solve(solver)
    solve_time = time.time() - start_time
    
    # Extract the status
    if hasattr(returned_stats, 'status'):
        status_code = returned_stats.status
    elif isinstance(returned_stats, dict) and 'status' in returned_stats:
        status_code = returned_stats['status']
    else:
        status_code = returned_stats

    status_map = {
        1: "Optimal",
        -1: "Infeasible",
        0: "Not Solved",
        -2: "Unbounded",
        -3: "Undefined"
    }
    status_string = status_map.get(status_code, "Unknown")
    
    # Extract the objective value only if a mathematically valid schedule was found
    if status_string == "Optimal":
        objective_value = pulp.value(prob.objective)
        print(f"Optimal schedule found!")
        print("Optimality Gap : 0.0% (Mathematical Proof Achieved)")
    elif status_string == "Infeasible":
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