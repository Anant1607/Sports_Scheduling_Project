# `src/Test Project.py` — Automated Verification & Unit Tests

## Overview

`src/Test Project.py` is a lightweight, self-contained test script (no `pytest` dependency required) that verifies input validation, derived team sets, objective function coefficients, and independent schedule rule validation against the project's `input.xlsx`.

---

## How to Run

From the project root directory:

**Windows:**
```bat
python "src/Test Project.py"
```

**macOS / Linux:**
```bash
python3 "src/Test Project.py"
```

*(Keep quotes around `"src/Test Project.py"` because the filename contains a space.)*

When executed as `__main__`, the script automatically discovers and runs every function in `globals()` whose name begins with `test_`, printing `PASS <test_name>` after each passing test.

### Optional Environment Variable
* **`OLD_SCHEDULE`**: If set to the path of a legacy schedule CSV file, `test_validator_catches_known_violations()` validates that CSV and asserts that `"Rule 8"` violations are detected instead of running a live solve.

---

## Test Cases Breakdown

| Test Function | What It Verifies |
| :--- | :--- |
| `test_validator_catches_known_violations` | Solves the unmodified model and asserts the optimal schedule passes all active rules (`[]`). Then mutates the schedule deterministically to confirm `validator.validate_schedule()` catches violations of **Rule 2** (duplicate team in a round), **Rule 12** (classic match outside `classic_window`), and **Rule 19** (rivalry match outside `rivalry_window`). If `OLD_SCHEDULE` is set, verifies that `"Rule 8"` is flagged on that legacy CSV. |
| `test_one_sided_rival_pair_is_found` | Sets `T8`'s `RivalTeamID` to `"None"` (leaving only `T6 -> T8`), asserts `validate_input()` emits an `"One-sided rivalry"` warning, and confirms `derive_sets()` still records `frozenset(("T6", "T8"))` in `rivals`. |
| `test_bad_inputs_are_rejected` | Verifies that `validate_input()` raises `ValueError` for: missing `Group` column, odd team count ($7$), duplicate `TeamID`, unknown rival (`T99`), chained conflicting rivals (`T6 -> T3 -> T5`), two teams claiming the same blank rival (`T6 -> T3` and `T2 -> T3`), and self-rivalry (`T3 -> T3`). |
| `test_popular_teams_come_from_sorted_scores` | Verifies that shuffling `input.xlsx` rows does not alter `popular` (`["T1", "T2", "T3"]`) or `revenue_pair` (`("T1", "T2")`), raising `T8`'s score to $120$ updates both lists, and overriding `n_popular: 4` returns $4$ teams. |
| `test_strong_teams_come_from_binary_flag` | Verifies `IsStrong` set derivation, rejection of non-binary flags (`IsStrong = 2`, `IsWeak = 2`, `IsTourist = 2`), and rejection of a team flagged as both strong and weak (`IsStrong = 1` and `IsWeak = 1`). |
| `test_tie_at_cutoff_warns` | Sets `T6` and `T7` to `PopularityScore = 85` at the top-3 cut-off boundary and verifies `derive_sets()` emits a tie warning. |
| `test_non_numeric_score_is_rejected` | Replaces a `PopularityScore` entry with `"high"` and confirms `validate_input()` raises `ValueError` (`"must be a number"`). |
| `test_objective_matches_original_formula` | Inspects the built PuLP objective dictionary to verify same-group round weights ($\{5: 1, 6: 15, 7: 6\}$, absent in round $4$) and early-round tourist hosting bonuses using $\frac{s_{\text{host}} + s_{\text{guest}}}{200} \times 6$ in rounds $1$–$3$ only. |

---

## Expected Console Output

When all tests pass, the script prints:

```text
PASS test_validator_catches_known_violations
PASS test_one_sided_rival_pair_is_found
PASS test_bad_inputs_are_rejected
PASS test_popular_teams_come_from_sorted_scores
PASS test_strong_teams_come_from_binary_flag
PASS test_tie_at_cutoff_warns
PASS test_non_numeric_score_is_rejected
PASS test_objective_matches_original_formula
```

---

## Notes on Input Data Assumptions

Several tests (`test_popular_teams_come_from_sorted_scores`, `test_strong_teams_come_from_binary_flag`, `test_one_sided_rival_pair_is_found`, `test_bad_inputs_are_rejected`, and `test_objective_matches_original_formula`) are written against the default 8-team `input.xlsx` dataset (`T1`–`T8`, with `T1`/`T2` strong, `T1`/`T2`/`T3` top 3 popular, `T5`/`T6` tourist hosts, and rival pairs `T3 <-> T5` and `T6 <-> T8`). If you heavily modify the default `input.xlsx` team IDs or flags, run the test suite against the baseline `input.xlsx` or update those test assertions accordingly.