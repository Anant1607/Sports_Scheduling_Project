# `src/extractor.py` — Schedule Extraction

## Overview

`src/extractor.py` translates solved PuLP binary decision variables from `model.build_model()` into a clean, sorted `pandas.DataFrame` representing the league fixture list.

---

## Constants

### `COLUMNS`
```python
COLUMNS = ["Round", "Home", "Away"]
```
Defines the canonical column schema and order returned by `extract_schedule()`.

---

## Function Reference

### `extract_schedule(x, dummy_team=None) -> pd.DataFrame`

Iterates over the solved nested variable dictionary `x[home_team][away_team][round_num]` and extracts every scheduled fixture.

#### Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `x` | `dict` | *(required)* | Nested dictionary where `x[home_team][away_team][round_num]` is a solved PuLP binary `LpVariable`. |
| `dummy_team` | `str \| None` | `None` | Optional `TeamID` representing a dummy/bye placeholder for odd-team leagues. Leave as `None` for standard even-team leagues (as enforced by `model.validate_input()`). |

#### Returns
* **`pd.DataFrame`** with columns `["Round", "Home", "Away"]`, sorted in ascending order by `Round` and then `Home`, with a clean $0$-based integer index.

---

## Implementation Details

1. **Floating-Point Thresholding:**
   MIP solvers can return near-binary floating-point values such as $0.9999999$ or $1 \times 10^{-9}$ instead of exact integers $1$ and $0$. The extractor safely checks:
   ```python
   if value is None or value <= 0.5:
       continue
   ```
   Variables with value $> 0.5$ are recorded as scheduled matches.

2. **Dummy / Bye Team Support:**
   If `dummy_team` is provided:
   * When `home_team == dummy_team`, the row is recorded as `{"Round": round_num, "Home": away_team, "Away": "Bye"}`.
   * When `away_team == dummy_team`, the row is recorded as `{"Round": round_num, "Home": home_team, "Away": "Bye"}`.
   * Otherwise, the match is recorded as `{"Round": round_num, "Home": home_team, "Away": away_team}`.

3. **Downstream Enrichment (in `src/main.py`):**
   `extract_schedule()` intentionally returns only team IDs (`Round`, `Home`, `Away`) so the DataFrame can be passed directly into `validator.validate_schedule()`. Afterward, `src/main.py` checks whether `TeamName` exists in `input.xlsx` and inserts `Home_Name` (column index 2) and `Away_Name` (column index 4) before exporting `outputs/schedule.csv`.

---

## Usage Example

```python
import extractor
import model
import solver

prob, x = model.build_model(df_teams)
status, _, _ = solver.run_exact_solver(prob)

if status == "Optimal":
    schedule_df = extractor.extract_schedule(x)
    print(schedule_df.head())
```