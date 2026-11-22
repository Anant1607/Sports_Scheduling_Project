# `src/validator.py` — Independent Schedule Validator

## Overview

`src/validator.py` provides an independent, post-solve audit of any generated schedule. Rather than inspecting PuLP constraints or solver variables, it reads only the finished `schedule_df` (`Round`, `Home`, `Away`) and the raw input DataFrame `df`, catching modeling mistakes or broken constraints independently of the optimizer.

---

## Function Reference

### `validate_schedule(schedule_df: pd.DataFrame, df: pd.DataFrame, config=None) -> list[str]`

Checks a completed schedule against every active league rule.

#### Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `schedule_df` | `pd.DataFrame` | *(required)* | Schedule containing at least the columns `Round`, `Home`, and `Away`. |
| `df` | `pd.DataFrame` | *(required)* | Team input table (same schema as `input.xlsx`). Validated via `model.validate_input(df)`. |
| `config` | `dict \| None` | `None` | Optional overrides merged onto `model.DEFAULTS`. Must match the config passed to `model.build_model()` if customized. |

#### Returns
* **`list[str]`**: A list of human-readable violation strings prefixed by their rule number (e.g., `"Rule 8: ..."`). An empty list `[]` indicates that every rule passed.

---

## Internal Lookup Structures

Before running rule checks, `validate_schedule()` indexes `schedule_df` into three dictionaries and three helper closures:
* `opp_home[t][k]` — Opponent hosted by team `t` in round `k`.
* `opp_away[t][k]` — Host visited by team `t` in round `k`.
* `matches_per_round[t][k]` — Total number of appearances of team `t` in round `k`.
* `is_home(t, k)`, `is_away(t, k)`, and `host_of(t, k)` — Convenience helpers for querying match venue and location.

---

## Rules Verified

| Rule Prefix | Check Performed |
| :--- | :--- |
| `Rule 1:` | Every unordered pair of teams $\{a, b\}$ meets exactly once across the season. |
| `Rule 2:` | Every team plays exactly $1$ match in every round $k \in \{1, \dots, n-1\}$. |
| `Rule 3:` | Each team's total home count lies within $[\lfloor (n-1)/2 \rfloor, \lceil (n-1)/2 \rceil]$. |
| `Rule 4:` | No team plays $m + 1$ consecutive home games ($m = \text{max\_consecutive}$). |
| `Rule 5:` | No team plays $m + 1$ consecutive away games. |
| `Rule 7:` | Each team hosts between $\lfloor c/2 \rfloor$ and $\lceil c/2 \rceil$ of its $c$ group mates. |
| `Rule 8:` | No team in a far region (`North`/`South`) visits the opposite far region during back-to-back away games. |
| `Rule 9/10:` | During any two consecutive away games, at least one game is played in the team's own region. |
| `Rule 11:` | Every team outside the top-2 `revenue_pair` hosts exactly $1$ of those two popular teams. |
| `Rule 12:` | Every classic match (both teams in `popular`) falls inside `classic_window`. |
| `Rule 13:` | Each popular team hosts between $\lfloor (|P|-1)/2 \rfloor$ and $\lceil (|P|-1)/2 \rceil$ classics. |
| `Rule 14:` *(Disabled)* | Commented out to mirror `src/model.py` (would check that two popular teams do not simultaneously play in `North` and `South`). |
| `Rule 16:` | No weak team (`IsWeak == 1`) plays strong teams (`IsStrong == 1`) in two consecutive rounds. |
| `Rule 19:` | Every rival pair meets inside `rivalry_window` (clamped to $[1, n-1]$). |
| `Rule 25:` | Every team in a far region (with $\ge 2$ teams) hosts at least one team from its own region. |

---

## Integration in `src/main.py`

Immediately after `extractor.extract_schedule()` runs, `src/main.py` executes:
```python
problems = validator.validate_schedule(schedule_df, df_teams)
```
If `problems` is non-empty, `main.py` prints every violation under `[!] The schedule breaks N rule(s). This is a model bug:` so modeling regressions are surfaced immediately.