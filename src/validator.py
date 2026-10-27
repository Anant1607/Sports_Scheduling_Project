# validator.py
#
# Independent rule check of a finished schedule. It reads only the schedule
# and the input data, never the solver, so it catches modelling mistakes.

import pandas as pd

from model import DEFAULTS, derive_sets, validate_input


def validate_schedule(schedule_df: pd.DataFrame, df: pd.DataFrame, config=None):
    """Return a list of human-readable violations. An empty list means all rules hold."""
    cfg = {**DEFAULTS, **(config or {})}
    validate_input(df)
    S = derive_sets(df)

    teams = S["teams"]
    region_of, group_of, popular = S["region_of"], S["group_of"], S["popular"]
    n_rounds = len(teams) - 1
    rounds = list(range(1, n_rounds + 1))
    last = n_rounds
    problems = []

    # opp_home[t][k] = opponent when t is home; opp_away[t][k] = host when t is away
    opp_home = {t: {} for t in teams}
    opp_away = {t: {} for t in teams}
    for _, row in schedule_df.iterrows():
        opp_home[row.Home][int(row.Round)] = row.Away
        opp_away[row.Away][int(row.Round)] = row.Home

    def is_home(t, k):
        return k in opp_home[t]

    def host_of(t, k):
        return t if is_home(t, k) else opp_away[t].get(k)

    # ---- rules 1 and 2 ----
    seen = {}
    for _, row in schedule_df.iterrows():
        pair = frozenset((row.Home, row.Away))
        seen[pair] = seen.get(pair, 0) + 1
    for a in teams:
        for b in teams:
            if a < b and seen.get(frozenset((a, b)), 0) != 1:
                problems.append(f"Rule 1: {a} and {b} meet {seen.get(frozenset((a, b)), 0)} times")
    for t in teams:
        for k in rounds:
            if is_home(t, k) + (k in opp_away[t]) != 1:
                problems.append(f"Rule 2: {t} does not play exactly once in round {k}")

    # ---- rule 3: home count ----
    low, high = n_rounds // 2, (n_rounds + 1) // 2
    for t in teams:
        n_home = sum(is_home(t, k) for k in rounds)
        if not low <= n_home <= high:
            problems.append(f"Rule 3: {t} has {n_home} home games (allowed {low}-{high})")

    # ---- rules 4/5: runs ----
    m = cfg["max_consecutive"]
    for t in teams:
        for k in range(1, n_rounds - m + 1):
            window = range(k, k + m + 1)
            if all(is_home(t, r) for r in window):
                problems.append(f"Rule 4: {t} plays {m + 1} home games from round {k}")
            if all(not is_home(t, r) for r in window):
                problems.append(f"Rule 5: {t} plays {m + 1} away games from round {k}")

    # ---- rule 7: group home balance ----
    for t in teams:
        mates = [j for j in S["groups"][group_of[t]] if j != t]
        n_home = sum(1 for k in rounds if opp_home[t].get(k) in mates)
        if not len(mates) // 2 <= n_home <= (len(mates) + 1) // 2:
            problems.append(f"Rule 7: {t} hosts {n_home} of {len(mates)} group rivals")

    # ---- rule 8: far-region trips ----
    far_a, far_b = cfg["far_regions"]
    for own, other in ((far_a, far_b), (far_b, far_a)):
        for t in [t for t in teams if region_of[t] == own]:
            for k in range(1, n_rounds):
                if not is_home(t, k) and not is_home(t, k + 1):
                    for r in (k, k + 1):
                        if region_of[opp_away[t][r]] == other:
                            problems.append(
                                f"Rule 8: {t} ({own}) visits {opp_away[t][r]} ({other}) "
                                f"in round {r} during back-to-back away games"
                            )

    # ---- rules 9/10: one of two consecutive away games in own region ----
    for t in teams:
        for k in range(1, n_rounds):
            if not is_home(t, k) and not is_home(t, k + 1):
                if all(region_of[opp_away[t][r]] != region_of[t] for r in (k, k + 1)):
                    problems.append(
                        f"Rule 9/10: {t} has two away games outside {region_of[t]} "
                        f"in rounds {k}-{k + 1}"
                    )

    # ---- rule 11: revenue balance ----
    if S["revenue_pair"]:
        a, b = S["revenue_pair"]
        for h in teams:
            if h not in (a, b):
                hosted = sum(opp_home[h].get(k) in (a, b) for k in rounds)
                if hosted != 1:
                    problems.append(f"Rule 11: {h} hosts {hosted} of {a}/{b} (must be 1)")

    # ---- rules 12/13: classics ----
    if len(popular) >= 2:
        w_start, w_end = cfg["classic_window"]
        for _, row in schedule_df.iterrows():
            if row.Home in popular and row.Away in popular:
                if not w_start <= int(row.Round) <= w_end:
                    problems.append(f"Rule 12: classic {row.Home}-{row.Away} in round {row.Round}")
        opponents = len(popular) - 1
        for p in popular:
            hosted = sum(1 for o in opp_home[p].values() if o in popular)
            if not opponents // 2 <= hosted <= (opponents + 1) // 2:
                problems.append(f"Rule 13: {p} hosts {hosted} classics")

        # ---- rule 14: broadcast units ----
        for k in rounds:
            regions_now = {p: region_of[host_of(p, k)] for p in popular}
            for p in popular:
                for q in popular:
                    if p != q and regions_now[p] == far_a and regions_now[q] == far_b:
                        problems.append(
                            f"Rule 14: round {k}: {p} plays in {far_a} while {q} plays in {far_b}"
                        )

    # ---- rule 16: strong teams ----
    def plays_strong(t, k):
        other = opp_home[t].get(k) or opp_away[t].get(k)
        return other in S["strong"]

    for t in teams:
        for k in range(1, n_rounds):
            if plays_strong(t, k) and plays_strong(t, k + 1):
                problems.append(f"Rule 16: {t} meets strong teams in rounds {k} and {k + 1}")

    # ---- rule 19: rivalries ----
    r_start, r_end = max(1, cfg["rivalry_window"][0]), min(last, cfg["rivalry_window"][1])
    for pair in S["rivals"]:
        i, j = sorted(pair)
        for _, row in schedule_df.iterrows():
            if {row.Home, row.Away} == {i, j} and not r_start <= int(row.Round) <= r_end:
                problems.append(f"Rule 19: rivals {i}-{j} meet in round {row.Round}")

    # ---- rule 25: intra-regional home ----
    for region in cfg["far_regions"]:
        region_teams = [t for t in teams if region_of[t] == region]
        if len(region_teams) < 2:
            continue
        for t in region_teams:
            if not any(o in region_teams for o in opp_home[t].values()):
                problems.append(f"Rule 25: {t} never hosts another {region} team")

    # ---- rule 22: tourists ----
    early = range(1, min(cfg["tourist_rounds"], last) + 1)
    for t in S["tourist"]:
        if not any(opp_home[t].get(k) in popular for k in early):
            problems.append(f"Rule 22: tourist team {t} hosts no popular team early")

    # ---- rule 24: last round cap ----
    n_last = sum(
        1 for _, row in schedule_df[schedule_df.Round == last].iterrows()
        if group_of[row.Home] == group_of[row.Away]
    )
    if n_last > cfg["last_round_group_cap"]:
        problems.append(f"Rule 24: {n_last} same-group games in the last round")

    # ---- optional rules ----
    for p in popular:
        for k in range(1, min(cfg["outlying_rounds"], last) + 1):
            if k in opp_away[p] and opp_away[p][k] in S["outlying"]:
                problems.append(f"Rule 15: {p} visits outlying {opp_away[p][k]} in round {k}")
    for pair in S["crossed"]:
        i, j = sorted(pair)
        for k in rounds:
            if is_home(i, k) == is_home(j, k):
                problems.append(f"Rule 18: crossed teams {i}/{j} both {'home' if is_home(i, k) else 'away'} in round {k}")
    for t in S["not_ready"]:
        if is_home(t, 1):
            problems.append(f"Rule 23: {t} is home in round 1")

    return problems