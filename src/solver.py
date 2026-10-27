# solver.py

import time

import pulp

STATUS_MAP = {
    1: "Optimal",
    0: "Not Solved",
    -1: "Infeasible",
    -2: "Unbounded",
    -3: "Undefined",
}


def run_exact_solver(prob, time_limit=None, gap_rel=0.0, msg=True):
    """
    Solve the model with HiGHS.

    time_limit : seconds, or None for no limit. Without a limit and with
                 gap_rel=0 an "Optimal" status is a proof of optimality.
    gap_rel    : relative MIP gap. HiGHS stops at 0.01% by default, so it is
                 set to 0 here to make the proof exact.

    Returns (status_string, solve_time_seconds, objective_value or None).
    """
    print("Initializing HiGHS solver...")
    solver = pulp.getSolver("HiGHS", msg=msg, gapRel=gap_rel, timeLimit=time_limit)

    print("Executing branch-and-cut search...")
    start = time.time()
    returned = prob.solve(solver)
    solve_time = time.time() - start

    # PuLP versions differ: solve() returns an int or an object with .status.
    if hasattr(returned, "status"):
        status_code = returned.status
    elif isinstance(returned, dict) and "status" in returned:
        status_code = returned["status"]
    else:
        status_code = returned
    status = STATUS_MAP.get(status_code, f"Unknown ({status_code})")

    objective = None
    if status == "Optimal":
        objective = pulp.value(prob.objective)
        if time_limit is None and gap_rel == 0.0:
            print("Optimal schedule found (proven, relative gap 0).")
        else:
            print(
                "Solver reports Optimal, but a time limit or gap tolerance was set, "
                "so the optimality proof is only valid within those settings."
            )
    elif status == "Infeasible":
        print("The constraints contradict each other: no schedule exists.")
    else:
        print(f"Solver stopped without a schedule. Status: {status}")

    print("-" * 30)
    print(f"Final Status   : {status}")
    print(f"Solve Time     : {solve_time:.4f} seconds")
    if objective is not None:
        print(f"Objective Value: {objective}")
    print("-" * 30)

    return status, solve_time, objective