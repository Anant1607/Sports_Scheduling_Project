# Operations Research Sports League Scheduler

An Integer Linear Programming (ILP) sports scheduling tool built in Python using **PuLP** and the **HiGHS** exact solver. The model is adapted from Durán et al. (2007), *"Scheduling the Chilean Soccer League by Integer Programming"* (*Interfaces* 37(6)), and scaled for a single round-robin league.

The workflow is designed for non-technical users: edit team data in `input.xlsx`, double-click a single launcher script (`run.bat` on Windows or `run.command` on macOS), and refresh the formatted `Output.xlsx` workbook—which can remain open while the optimizer runs.

---

## Project Structure

```text
Sports_Scheduling_Project/
├── input.xlsx              # User-editable league configuration & team attributes
├── Output.xlsx             # Formatted output workbook linked to outputs/schedule.csv via Power Query
├── run.bat                 # Windows one-click launcher
├── run.command             # macOS one-click launcher
├── outputs/
│   └── schedule.csv        # Generated schedule (created/overwritten automatically on each run)
└── src/
    ├── __init__.py         # Package marker
    ├── main.py             # CLI entry point (reads Excel, solves, validates, writes CSV)
    ├── model.py            # Input validation, set derivation, objective & ILP constraints
    ├── solver.py           # Exact HiGHS solver wrapper (0% MIP gap by default)
    ├── extractor.py        # Converts solved binary variables into a sorted schedule DataFrame
    ├── validator.py        # Independent rule checker that verifies the output schedule
    └── Test Project.py     # Unit tests for validation, sets, and rules
```

---

## Prerequisites & Installation

### 1. Install Python
Install **Python 3.9 or higher** from [python.org](https://www.python.org/downloads/).
* **Windows:** During installation, check **"Add python.exe to PATH"**.
* **macOS:** Python 3 can be installed via [python.org](https://www.python.org/downloads/) or Homebrew (`brew install python`).

### 2. Install Required Python Packages
Open a terminal (Command Prompt / PowerShell on Windows, or Terminal on macOS) and install the required libraries:

**Windows:**
```bat
pip install pandas openpyxl pulp highspy
```

**macOS:**
```bash
pip3 install pandas openpyxl pulp highspy
```

*(Note: `openpyxl` is required by `pandas` to read `.xlsx` files, and `highspy` provides the HiGHS MIP solver backend used by PuLP.)*

---

## Input Format (`input.xlsx`)

Edit `input.xlsx` in the project root folder and save it before running the scheduler. Every row represents one team.

| Column | Required | Allowed Values | Description |
| :--- | :---: | :--- | :--- |
| `TeamID` | Yes | Unique string (e.g., `T1`) | Unique identifier for each team. |
| `TeamName` | No | String | Optional display name. If present, `Home_Name` and `Away_Name` are added to `schedule.csv`. |
| `Region` | Yes | String (e.g., `North`, `Central`, `South`) | Geographic region used for travel and intra-regional rules. |
| `Group` | Yes | String / Number | Group assignment used for late-round rewards and group home balance. |
| `PopularityScore` | Yes | Numeric (0–100 scale) | Determines top popular teams, revenue pair, and tourist bonuses. |
| `IsStrong` | Yes | `0` or `1` | Flags strong teams (cannot be `1` if `IsWeak` is `1`). |
| `IsWeak` | Yes | `0` or `1` | Flags weak teams (cannot play strong teams in consecutive rounds). |
| `IsTourist` | Yes | `0` or `1` | Flags tourist-destination teams that earn early-round hosting bonuses. |
| `RivalTeamID` | Yes | Valid `TeamID`, blank, or `None` | Paired rival team that must be played inside the rivalry round window. |

**Key Input Rules:**
* The total number of teams must be **even and at least 4**.
* `TeamID` values cannot be duplicated.
* A team cannot be both strong (`IsStrong = 1`) and weak (`IsWeak = 1`).
* A team cannot list itself as its own rival, and conflicting/chained rivalries (e.g., `T6 -> T3` while `T3 -> T5`) are rejected. One-sided rivalries emit a warning and are automatically treated as symmetric.

---

## How to Run

### Important Folder Placement Rule (Windows)
Keep the entire `Sports_Scheduling_Project` folder in a **local directory outside of OneDrive** (for example, `C:\Sports_Scheduling_Project`). Do **not** place it inside a OneDrive-synced `Desktop` or `Documents` folder, or Excel's dynamic relative path will break (see Troubleshooting below).

---

### Running on Windows (Recommended Full Workflow)

1. Open `input.xlsx`, make your edits, and **Save** (`Ctrl + S`).
2. Double-click **`run.bat`** in the project root folder.
   * The console window will validate the input, solve the ILP using HiGHS, run the independent rule validator, and write `outputs\schedule.csv`.
   * Wait until you see `[+] Schedule written to ...` and press any key to close the console.
3. Open **`Output.xlsx`** (you may also leave it open while `run.bat` runs).
   * If a yellow **Security Warning** bar appears at the top, click **Enable Content**.
4. Go to the **Data** tab and click **Refresh All**.
   * Your formatted schedule table on the `schedule` sheet will update automatically while preserving all styling and layout.

---

### Running on macOS

1. **First-Time Setup (Make the Launcher Executable):**
   Open Terminal, navigate to the project folder, and run:
   ```bash
   chmod +x run.command
   ```
2. Open `input.xlsx`, make your edits, and **Save** (`Cmd + S`).
3. Double-click **`run.command`** (or run `python3 src/main.py` in Terminal) to generate `outputs/schedule.csv`.
4. **Viewing the Output on macOS:**
   * Because **Excel for Mac** does not support dynamic relative local file paths in Power Query (it raises an *"on-premises data gateway"* error), **Refresh All** inside `Output.xlsx` will only work automatically on Windows.
   * On macOS, you have two ways to view the updated schedule:
     1. Open `outputs/schedule.csv` directly in Excel, Numbers, or VS Code.
     2. Temporarily point Power Query to your static Mac path (see the macOS Power Query troubleshooting entry below), **without saving over the dynamic query** before sharing back to Windows users.

---

### Running from Command Line (Advanced)

Both Windows and macOS support optional CLI arguments via `src/main.py`:

```bash
python src/main.py --input path/to/input.xlsx --output path/to/schedule.csv --time-limit 60
```

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--input` | `<PROJECT_ROOT>/input.xlsx` | Path to the input Excel workbook. |
| `--output` | `<PROJECT_ROOT>/outputs/schedule.csv` | Destination path for the CSV schedule. |
| `--time-limit` | `None` (no limit) | Optional solver time limit in seconds. |

**Exit Codes:**
* `0`: Optimal schedule found and written to CSV.
* `1`: Input file missing or failed validation.
* `2`: Model is infeasible or solver stopped without a solution (writes an empty CSV).

---

## Mathematical Model Summary

Let $T$ be the set of $n$ teams ($n \ge 4$, even) and $K = \{1, 2, \dots, n - 1\}$ be the set of rounds.

**Decision Variable:**
$$x_{i,j,k} \in \{0, 1\} \quad \forall i, j \in T \; (i \neq j), \; k \in K$$
where $x_{i,j,k} = 1$ if team $i$ hosts team $j$ in round $k$, and $0$ otherwise.

**Objective Function (Maximize):**
1. **Late-Round Group Games:** Rewards matches between teams in the same group during late rounds (default weights: Round 5 = $1$, Round 6 = $15$, Round 7 = $6$).
2. **Tourist Hosting Bonus:** Rewards tourist teams ($i \in T_{\text{tourist}}$) hosting games in early rounds (default rounds $1, 2, 3$) by:
   $$\text{bonus}_{i,j} = \frac{\text{PopularityScore}_i + \text{PopularityScore}_j}{200} \times \text{tourist\_bonus\_max}$$
   (default $\text{tourist\_bonus\_max} = 6$).

**Active Constraints (Default Configuration for an 8-Team, 7-Round League):**
* **Rule 1 (Single Round-Robin):** Every pair of teams meets exactly once.
* **Rule 2 (One Match per Round):** Every team plays exactly one game in each round.
* **Rule 3 (Home/Away Balance):** Each team plays between $\lfloor (n-1)/2 \rfloor$ and $\lceil (n-1)/2 \rceil$ home games.
* **Rules 4 & 5 (Consecutive Runs):** At most `max_consecutive` ($2$) consecutive home games or consecutive away games.
* **Rule 7 (Group Home Balance):** Each team hosts approximately half of its intra-group opponents.
* **Rule 8 (Far-Region Travel):** A `North` or `South` team cannot visit the opposite far region during two consecutive away games.
* **Rules 9 & 10 (Own-Region Away Rule):** During any two consecutive away games, at least one must be played in the team's own region.
* **Rule 11 (Revenue Balance):** Every team (except the top 2 most popular teams) hosts exactly one of the two most popular teams.
* **Rules 12 & 13 (Classics):** Matches among the top `n_popular` ($3$) popular teams occur only inside `classic_window` (rounds $3$–$6$), and each popular team hosts approximately half of its classics.
* **Rule 16 (Strong vs. Weak):** No weak team plays strong teams in two consecutive rounds.
* **Rule 19 (Rivalries):** Paired rival teams meet inside `rivalry_window` (rounds $4$–$6$).
* **Rule 25 (Intra-Regional Home Games):** Every `North` and `South` team hosts at least one team from its own region.
* *(Rule 14 — Broadcast Units — is commented out in `src/model.py` and `src/validator.py` to avoid infeasibility on small league sizes.)*

All default parameters can be overridden via the `DEFAULTS` dictionary in `src/model.py`.

---

## Troubleshooting & Potential Errors

### 1. Excel & Power Query Errors (Windows)

| Error / Symptom | Cause | Fix |
| :--- | :--- | :--- |
| **Path error showing `https://d.docs.live.net/...` or `Could not find file`** | The project folder is inside a **OneDrive-synced** directory (`Desktop`, `Documents`, etc.), causing `CELL("filename", A1)` to return a web URL instead of a local drive path. | Move the entire project folder to a plain local directory outside OneDrive (e.g., `C:\Sports_Scheduling_Project`), reopen `Output.xlsx`, and click **Refresh All**. |
| **`Formula.Firewall: Query references other queries or steps...`** | Excel's privacy engine blocks combining an internal cell (`Excel.CurrentWorkbook`) with a local file (`File.Contents`). | Go to **Data -> Get Data -> Query Options -> CURRENT WORKBOOK -> Privacy**, select **Ignore the Privacy Levels and potentially improve performance**, click **OK**, and save `Output.xlsx`. |
| **Yellow bar: `Security Warning: External Data Connections have been disabled`** | Excel blocks external CSV connections on newly downloaded or copied workbooks by default. | Click **Enable Content** on the yellow banner before clicking **Refresh All**. |
| **`DataFormat.Error` or missing columns on refresh** | `outputs/schedule.csv` is empty (usually because the last solver run was infeasible) or `main.py` has not been run yet. | Run `run.bat` and verify `outputs/schedule.csv` contains valid rows before refreshing Excel. |
| **Formatting or column widths reset after Refresh All** | Table external data properties are not locked. | Click inside the schedule table -> **Table Design -> Properties** -> check **Preserve cell formatting** and **Preserve column sort/filter/layout**, uncheck **Adjust column width**, click **OK**, and save. |
| **Excel shows old schedule after running `run.bat`** | Excel does not auto-refresh CSV links until triggered. | Click **Data -> Refresh All** (`Ctrl + Alt + F5`) inside `Output.xlsx`. |

---

### 2. Excel & Script Errors (macOS)

| Error / Symptom | Cause | Fix |
| :--- | :--- | :--- |
| **`An on-premises data gateway is required to connect` in Power Query** | Known **Excel for Mac** limitation: macOS Excel's Power Query engine blocks dynamic local file paths constructed from `Excel.CurrentWorkbook()` and only permits hardcoded static paths. | Either view `outputs/schedule.csv` directly on Mac, or temporarily replace `FilePath` in **Data -> Get Data (Power Query) -> Launch Power Query Editor -> Home -> Advanced Editor** with your static path (e.g., `"/Users/<you>/.../outputs/schedule.csv"`). **Do not save over** the dynamic query if sharing `Output.xlsx` back to Windows teammates. |
| **macOS prompts `Grant File Access` on refresh** | macOS App Sandbox requires explicit folder access the first time Excel reads a local file. | Click **Select**, choose your `Sports_Scheduling_Project` folder, and click **Grant Access**. |
| **`run.command` says `The file could not be executed because you do not have appropriate access privileges`** | Executable bit was stripped when copying/zipping the folder. | Open Terminal in the project root and run `chmod +x run.command`. |
| **macOS Gatekeeper blocks `run.command` ("cannot be opened because it is from an unidentified developer")** | macOS security policy for downloaded scripts. | Right-click (or Control-click) `run.command`, click **Open**, and confirm **Open** in the dialog. Alternatively, run `python3 src/main.py` in Terminal. |

---

### 3. Script & Python Environment Errors (Windows & macOS)

| Error / Symptom | Cause | Fix |
| :--- | :--- | :--- |
| **`'python' is not recognized as an internal or external command` (Windows)** | Python was not added to the system `PATH`, or only the `py` launcher is registered. | Reinstall Python with **"Add python.exe to PATH"** checked, or change `python src/main.py` in `run.bat` to `py src/main.py`. |
| **`Error: could not find .../src/main.py` when launching `run.bat`** | Running the batch file from a shortcut or different working directory without changing directory first. | Ensure `run.bat` begins with `@echo off` followed by `cd /d "%~dp0"` before `python src/main.py`. |
| **`ModuleNotFoundError: No module named 'pandas'` / `'pulp'` / `'openpyxl'`** | Required Python dependencies are not installed in the active Python interpreter. | Run `pip install pandas openpyxl pulp highspy` (Windows) or `pip3 install pandas openpyxl pulp highspy` (macOS). |
| **`PulpSolverError: PuLP: cannot execute HiGHS` / solver not found** | HiGHS solver bindings are missing from your Python environment. | Install `highspy` via `pip install highspy` (or `pip3 install highspy`) and ensure `pulp` is up to date (`pip install --upgrade pulp`). |
| **`PermissionError: [Errno 13] Permission denied: '.../outputs/schedule.csv'`** | `outputs/schedule.csv` itself is currently open directly in Excel on Windows (which locks the file for writing). | Close `schedule.csv` before running `run.bat`. *(Note: Leaving `Output.xlsx` open is fine; only opening the raw `.csv` file directly locks it.)* |

---

### 4. Input Validation & Solver Errors

| Error / Symptom | Cause | Fix |
| :--- | :--- | :--- |
| **`Error: invalid input. input is missing required column(s): [...]`** | A required header in `input.xlsx` was renamed, misspelled, or deleted. | Restore the exact column names listed in the **Input Format** table above (case-sensitive). |
| **`Error: invalid input. need an even number of teams (at least 4)`** | `input.xlsx` has fewer than 4 rows, an odd number of teams, or a stray blank/formatting row at the bottom. | Ensure an even number of teams ($\ge 4$) and delete any empty trailing rows in `input.xlsx`. |
| **`Error: invalid input. a team cannot be both strong and weak`** | A row has both `IsStrong = 1` and `IsWeak = 1`. | Set at least one of those flags to `0` for the listed team(s). |
| **`Error: invalid input. Conflicting RivalTeamID`** | Two teams claim the same rival, or a rival points to a third team (e.g., `T6 -> T3` while `T3 -> T5`). | Ensure rivalries form clean disjoint pairs (e.g., `T6 <-> T8`), or leave `RivalTeamID` blank / `None`. |
| **`[-] Model is infeasible: the rules cannot all hold together.`** | The combination of input attributes (e.g., too many strong/weak teams, unbalanced regions/groups, or impossible travel rules) has no valid schedule satisfying every constraint simultaneously. | Review your changes in `input.xlsx` (especially `Region`, `Group`, `IsStrong`/`IsWeak`, and `RivalTeamID`), or relax round windows/rules in `src/model.py`. Note that an infeasible run overwrites `outputs/schedule.csv` with an empty file. |
| **Warning: `PopularityScore: ... tie at the cut-off for the top 3`** | Two teams tie at the boundary of the top `n_popular` teams, so row order in `input.xlsx` breaks the tie. | Adjust one team's `PopularityScore` slightly (e.g., by `1`) to make the popular set unambiguous. |
