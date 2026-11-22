# `src/solver.py` — Exact HiGHS MIP Solver Wrapper

## Overview

`src/solver.py` encapsulates the execution of the **HiGHS** Mixed-Integer Programming (MIP) solver through PuLP, measures wall-clock solve time, normalizes solver status codes across PuLP versions, and prints a structured console report.

---

## Constants

### `STATUS_MAP`
Maps PuLP integer status codes to human-readable status strings:

| Code | Status String | Meaning |
| :---: | :--- | :--- |
| `1` | `"Optimal"` | A globally optimal feasible solution was found (within `gap_rel`). |
| `0` | `"Not Solved"` | The solver did not run or stopped before reaching a terminal status (e.g., hit `time_limit`). |
| `-1` | `"Infeasible"` | No schedule exists that satisfies all constraints simultaneously. |
| `-2` | `"Unbounded"` | The objective value can increase without bound. |
| `-3` | `"Undefined"` | Solver returned an undefined status. |

Any unrecognized code is formatted as `"Unknown (<code>)"`.

---

## Function Reference

### `run_exact_solver(prob, time_limit=None, gap_rel=0.0, msg=True) -> tuple[str, float, float | None]`

Solves a PuLP `LpProblem` using the HiGHS branch-and-cut solver.

#### Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `prob` | `pulp.LpProblem` | *(required)* | The optimization problem constructed by `model.build_model()`. |
| `time_limit` | `float \| None` | `None` | Maximum solve time in seconds. `None` disables the time limit. |
| `gap_rel` | `float` | `0.0` | Relative MIP optimality gap tolerance. HiGHS defaults to $0.01\%$ ($10^{-4}$), so setting `gap_rel=0.0` forces an exact proof of global optimality. |
| `msg` | `bool` | `True` | When `True`, streams live HiGHS solver logs to stdout. Set `False` for silent execution (e.g., in unit tests). |

#### Returns
A 3-tuple `(status, solve_time, objective)`:
* **`status`** (`str`): Mapped status label from `STATUS_MAP` (e.g., `"Optimal"`, `"Infeasible"`).
* **`solve_time`** (`float`): Elapsed wall-clock time in seconds (`time.time()`).
* **`objective`** (`float | None`): Objective value via `pulp.value(prob.objective)` when `status == "Optimal"`, otherwise `None`.

---

## Key Design Details

1. **Exact Optimality Guarantee:**
   When `status == "Optimal"`, the module explicitly checks whether `time_limit is None and gap_rel == 0.0`. If either a time limit or non-zero relative gap was passed, it prints a notice clarifying that optimality is only proven within those tolerances.

2. **Cross-Version PuLP Compatibility:**
   Different releases of PuLP return slightly different structures from `prob.solve(solver)`. `run_exact_solver()` safely extracts the status code whether the return value is:
   * An object exposing `.status`
   * A dictionary containing `"status"`
   * A plain integer status code

3. **Runtime Dependency:**
   Requires `highspy` (or a system HiGHS binary) to be installed so `pulp.getSolver("HiGHS", ...)` can instantiate the backend. If missing, PuLP raises a `PulpSolverError`.

---

## Console Output Example

```text
Initializing HiGHS solver...
Executing branch-and-cut search...
Optimal schedule found (proven, relative gap 0).
------------------------------
Final Status   : Optimal
Solve Time     : 0.1428 seconds
Objective Value: 54.75
------------------------------
```