# `src/model.py` — Optimization Model & Input Validation

## Overview

`src/model.py` defines the core Integer Linear Programming (ILP) formulation for the single round-robin sports league scheduler. It is adapted from Durán et al. (2007), *"Scheduling the Chilean Soccer League by Integer Programming"* (*Interfaces* 37(6)), and scaled for an 8-team, 7-round league by default.

The module handles three responsibilities:
1. Validating raw team data loaded from `input.xlsx`.
2. Deriving team subsets (popular teams, revenue pair, strong/weak/tourist teams, groups, and rivalries).
3. Constructing the PuLP `LpProblem` object with binary match decision variables, objective terms, and scheduling constraints.

---

## Configuration (`DEFAULTS`)

All scheduling parameters live in the module-level `DEFAULTS` dictionary and can be overridden by passing a custom dictionary to `build_model(df, config={...})` or `derive_sets(df, cfg={...})`.

| Key | Default Value | Description |
| :--- | :--- | :--- |
| `classic_window` | `(3, 6)` | Inclusive round window in which matches between popular teams ("classics") must take place. |
| `rivalry_window` | `(4, 6)` | Inclusive round window in which paired rivals (`RivalTeamID`) must meet. |
| `round_weights` | `{5: 1, 6: 15, 7: 6}` | Objective weights for intra-group matches by round number (unlisted rounds carry weight $0$). |
| `tourist_bonus_rounds` | `(1, 2, 3)` | Rounds during which tourist teams receive a hosting bonus. |
| `tourist_bonus_max` | `6` | Maximum possible bonus per hosted match for a tourist team. |
| `max_consecutive` | `2` | Maximum allowed consecutive home games or consecutive away games. |
| `far_regions` | `("North", "South")` | Pair of distant regions subject to travel and intra-regional hosting constraints (Rules 8, 14, 25). |
| `n_popular` | `3` | Number of highest-`PopularityScore` teams classified as popular. |

### `REQUIRED_COLUMNS`
```python
[
    "TeamID", "Region", "Group", "PopularityScore",
    "IsStrong", "IsWeak", "IsTourist", "RivalTeamID",
]
```

---

## Functions Reference

### `_clean_id(value)`
Normalizes optional identifier fields (used for `RivalTeamID`). Returns `None` for `NaN`, empty strings, or the literal text `"None"`; otherwise returns the stripped string.

### `validate_input(df: pd.DataFrame)`
Checks the input DataFrame before modeling and raises a descriptive `ValueError` if any condition fails:
* **Schema:** All columns in `REQUIRED_COLUMNS` must be present.
* **Numeric scores:** Every `PopularityScore` must coerce cleanly to a numeric value.
* **Binary flags:** `IsStrong`, `IsWeak`, and `IsTourist` must contain only `0` or `1`.
* **Uniqueness:** `TeamID` cannot have duplicate entries.
* **Mutual exclusivity:** A team cannot simultaneously have `IsStrong == 1` and `IsWeak == 1`.
* **League size:** Number of teams $n$ must be even and satisfy $n \ge 4$.
* **Rivalry integrity:**
  * Referenced rivals must exist in `TeamID`.
  * A team cannot list itself as its own rival.
  * Conflicting chains (e.g., `T6 -> T3` while `T3 -> T5`) and multiple teams claiming the same rival raise `ValueError`.
  * One-sided rivalries (e.g., `T6 -> T3` while `T3` lists no rival) emit a `UserWarning` and are treated symmetrically.

### `_top_n(teams, score, n, label)`
Sorts `teams` in descending order of `score` (preserving input sheet order on ties) and returns the top $n$. Emits a `UserWarning` if a tie occurs across the cut-off boundary between rank $n$ and rank $n + 1$.

### `derive_sets(df: pd.DataFrame, cfg=None) -> dict`
Computes all team sets and lookup mappings needed by both `build_model()` and `validator.validate_schedule()`:

| Returned Key | Type | Meaning |
| :--- | :--- | :--- |
| `teams` | `list[str]` | Ordered list of all `TeamID`s. |
| `score` | `dict[str, float]` | Mapping from `TeamID` to numeric `PopularityScore`. |
| `group_of` | `dict[str, Any]` | Mapping from `TeamID` to `Group`. |
| `region_of` | `dict[str, str]` | Mapping from `TeamID` to `Region`. |
| `groups` | `dict[Any, list[str]]` | Teams grouped by `Group`. |
| `popular` | `list[str]` | Top `n_popular` teams sorted by highest `PopularityScore` first. |
| `revenue_pair` | `tuple[str, str] \| None` | The top 2 most popular teams (`popular[:2]`), if at least 2 exist. |
| `strong` | `list[str]` | Teams with `IsStrong == 1`. |
| `weak` | `list[str]` | Teams with `IsWeak == 1`. |
| `tourist` | `list[str]` | Teams with `IsTourist == 1`. |
| `rivals` | `set[frozenset[str]]` | Deduplicated symmetric rival pairs. |

### `build_model(df: pd.DataFrame, config=None) -> tuple[pulp.LpProblem, dict]`
Validates `df`, derives team sets, builds the PuLP maximization model, and returns `(prob, x)`.

* **PuLP Version Compatibility:** Uses `prob.add_variable(...)` on PuLP 3.0+ and falls back to `pulp.LpVariable(...)` on older versions.
* **Internal Expression Helpers:**
  * `home(i, k)` $= \sum_{j \neq i} x_{i,j,k}$ (equals $1$ if team $i$ hosts in round $k$).
  * `away(i, k)` $= \sum_{j \neq i} x_{j,i,k}$ (equals $1$ if team $i$ plays away in round $k$).
  * `visits(t, k, hosts)` $= \sum_{h \in \text{hosts}, h \neq t} x_{h,t,k}$ (equals $1$ if team $t$ visits a host in `hosts` during round $k$).
  * `plays_in(t, k, region_teams)` (equals $1$ if team $t$ plays a match physically staged in that region during round $k$).

---

## Mathematical Formulation

Let $T$ be the set of $n$ teams ($n \ge 4$, even) and $K = \{1, 2, \dots, n - 1\}$ be the set of rounds.

### Decision Variables
$$x_{i,j,k} \in \{0, 1\} \quad \forall i, j \in T \; (i \neq j), \; k \in K$$
where $x_{i,j,k} = 1$ if team $i$ hosts team $j$ in round $k$, and $0$ otherwise. Because variables are only created for $i \neq j$, no explicit self-play constraint is required.

### Objective Function
Maximize the sum of late-round intra-group weights and early-round tourist hosting bonuses:
$$\max \sum_{\substack{i, j \in T,\, i \neq j \\ g(i) = g(j)}} \sum_{k \in K} w_k \, x_{i,j,k} \;+\; \sum_{i \in T_{\text{tourist}}} \sum_{j \in T \setminus \{i\}} \sum_{k \in K_{\text{tour}}} \left( \frac{s_i + s_j}{200} \cdot B_{\max} \right) x_{i,j,k}$$
where $w_k$ is `round_weights[k]`, $s_i$ is `PopularityScore` of team $i$, $K_{\text{tour}}$ is `tourist_bonus_rounds`, and $B_{\max}$ is `tourist_bonus_max`.

### Constraints Implemented

| Rule | Constraint Prefix | Mathematical / Logical Description |
| :--- | :--- | :--- |
| **Rule 1** | `SingleRoundRobin_` | $\sum_{k \in K} (x_{i,j,k} + x_{j,i,k}) = 1$ for every unordered pair $\{i, j\} \subset T$. |
| **Rule 2** | `OneMatchPerRound_` | $\text{home}(i, k) + \text{away}(i, k) = 1$ for every $i \in T, k \in K$. |
| **Rule 3** | `HomeCountMin_`, `HomeCountMax_` | $\lfloor (n-1)/2 \rfloor \le \sum_{k \in K} \text{home}(i, k) \le \lceil (n-1)/2 \rceil$ for all $i \in T$. |
| **Rules 4 & 5** | `MaxConsecutiveHome_`, `MaxConsecutiveAway_` | For any window of $m + 1$ consecutive rounds ($m = \text{max\_consecutive}$), at most $m$ home games and at most $m$ away games. |
| **Rule 7** | `GroupHomeMin_`, `GroupHomeMax_` | Each team hosts between $\lfloor c_i/2 \rfloor$ and $\lceil c_i/2 \rceil$ of its $c_i$ intra-group opponents. |
| **Rule 8** | `NoFarTrip_` | A team in a far region (`North`/`South`) cannot combine a visit to the opposite far region with an adjacent away game: $\text{visits}(t, a, R_{\text{other}}) + \text{away}(t, b) \le 1$ for adjacent rounds $(a, b)$. |
| **Rules 9 & 10** | `OwnRegionTrip_` | On any two consecutive away games, at least one must occur in the team's own region: $\text{visits}(t, k, T \setminus R_t) + \text{visits}(t, k+1, T \setminus R_t) \le 1$. |
| **Rule 11** | `RevenueBalance_` | Every team $h \notin \{a, b\}$ (the top 2 popular teams) hosts exactly one of $a$ or $b$. |
| **Rule 12** | `NoClassicInRound_` | For $k \notin [w_{\text{start}}, w_{\text{end}}]$, no two popular teams may play each other. |
| **Rule 13** | `ClassicHomeMin_`, `ClassicHomeMax_` | Each popular team hosts between $\lfloor (|P|-1)/2 \rfloor$ and $\lceil (|P|-1)/2 \rceil$ classic games. |
| **Rule 14** *(Disabled)* | `Broadcast_` | Commented out in `model.py` because forbidding simultaneous popular-team games in `North` and `South` causes infeasibility on smaller leagues. |
| **Rule 16** | `NoConsecutiveStrong_` | Modified to apply to weak teams only: no $i \in T_{\text{weak}}$ plays strong teams in both round $k$ and round $k + 1$. |
| **Rule 19** | `RivalryWindow_` | Every rival pair $\{i, j\}$ meets once inside $[r_{\text{start}}, r_{\text{end}}]$ (clamped to $[1, n-1]$). |
| **Rule 25** | `IntraRegionHome_` | Every team in a far region (`North`, `South`, provided that region has $\ge 2$ teams) hosts at least one team from its own region. |