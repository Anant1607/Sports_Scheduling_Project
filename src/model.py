# model.py
#
# Integer programming model for a single round-robin league schedule,
# adapted from Duran et al. (2007), "Scheduling the Chilean Soccer League
# by Integer Programming", Interfaces 37(6).
#
# Decision variable: x[i][j][k] = 1 if team i hosts team j in round k.
# Variables only exist for i != j, so no self-play constraint is needed.

import warnings

import pandas as pd
import pulp


# ============================================================
# 0. CONFIGURATION
# ============================================================
# Windows and thresholds are scaled for an 8-team, 7-round league.
# Override any of them with build_model(df, config={...}).

DEFAULTS = {
    # Classic matches between popular teams must fall in this round window.
    "classic_window": (3, 6),
    # Rival pairs (RivalTeamID column) must meet in this round window.
    "rivalry_window": (4, 6),
    # Objective, part 1: weight of a game between teams of the same group, by round.
    # Rounds not listed have weight 0. These are the original weights.
    "round_weights": {5: 1, 6: 6, 7: 15},
    # Objective, part 2: a tourist team that hosts any team in these rounds earns
    # ((popularity of host + popularity of guest) / 200) x tourist_bonus_max.
    "tourist_bonus_rounds": (1, 2, 3),
    "tourist_bonus_max": 10,
    # Longest allowed run of home games or away games.
    "max_consecutive": 2,
    # Regions used by the North/South rules (paper rules 8, 14, 25).
    "far_regions": ("North", "South"),
    # Popular teams = the n_popular teams with the highest PopularityScore.
    "n_popular": 3,
}

REQUIRED_COLUMNS = [
    "TeamID", "Region", "Group", "PopularityScore",
    "IsStrong", "IsWeak", "IsTourist", "RivalTeamID",
]


# ============================================================
# 1. INPUT VALIDATION AND SET CREATION
# ============================================================

def _clean_id(value):
    """Return a stripped string ID, or None for blanks, NaN and the text 'None'."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return None if text in ("", "None") else text


def validate_input(df: pd.DataFrame):
    """Raise ValueError with a readable message if the input cannot be modelled."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"input is missing required column(s): {missing}")

    values = pd.to_numeric(df["PopularityScore"], errors="coerce")
    if values.isna().any():
        bad = df.loc[values.isna(), "TeamID"].tolist()
        raise ValueError(f"PopularityScore must be a number for every team, check: {bad}")

    if not df["IsStrong"].isin([0, 1]).all():
        bad = df.loc[~df["IsStrong"].isin([0, 1]), "TeamID"].tolist()
        raise ValueError(f"IsStrong must be 0 or 1 for every team, check: {bad}")

    if not df["IsWeak"].isin([0, 1]).all():
        bad = df.loc[~df["IsWeak"].isin([0, 1]), "TeamID"].tolist()
        raise ValueError(f"IsWeak must be 0 or 1 for every team, check: {bad}")
    
    if not df["IsTourist"].isin([0, 1]).all():
        bad = df.loc[~df["IsTourist"].isin([0, 1]), "TeamID"].tolist()
        raise ValueError(f"IsTourist must be 0 or 1 for every team, check: {bad}")

    if df["TeamID"].duplicated().any():
        dupes = df.loc[df["TeamID"].duplicated(), "TeamID"].tolist()
        raise ValueError(f"duplicate TeamID value(s): {dupes}")

    both_strong_and_weak = df.loc[(df["IsStrong"] == 1) & (df["IsWeak"] == 1), "TeamID"].tolist()
    if both_strong_and_weak:
        raise ValueError(f"a team cannot be both strong and weak, check: {both_strong_and_weak}")

    n = len(df)
    if n < 4 or n % 2 != 0:
        raise ValueError(f"need an even number of teams (at least 4), got {n}")

    # Inside validate_input(df):
    ids = set(df["TeamID"])
    rival_map = {}
    if "RivalTeamID" in df.columns:
        for team, other in zip(df["TeamID"], df["RivalTeamID"]):
            other = _clean_id(other)
            if other is not None:
                if other not in ids:
                    raise ValueError(f"RivalTeamID of {team} refers to unknown team '{other}'")
                if other == team:
                    raise ValueError(f"Team {team} cannot be its own rival")
                rival_map[team] = other

        # Check for asymmetric / conflicting rivalries
        for team, other in rival_map.items():
            other_rival = rival_map.get(other)
            if other_rival is None:
                #warn that a one-sided rival will be treated symmetrically (eg T6 -> T3, while T3 -> None)
                warnings.warn(
                    f"One-sided rivalry: {team} lists {other} as rival, "
                    f"but {other} has no rival listed. Treating ({team}, {other}) as rivals."
                )
            # T6 -> T3, but T3 - T2
            elif other_rival != team:
                raise ValueError(
                    f"Conflicting RivalTeamID: {team} lists {other}, "
                    f"but {other} lists {other_rival} instead of {team}"
                )

        # Check that no team is targeted by two different teams (e.g. T6 -> T3 and T2 -> T3)
        incoming = {}
        for team, other in rival_map.items():
            if other in incoming and incoming[other] != team:
                raise ValueError(
                    f"Conflicting RivalTeamID: both {incoming[other]} and {team} list {other} as their rival"
                )
            incoming[other] = team


def _top_n(teams, score, n, label):
    """Sort teams by score, highest first, and return the first n.
    Ties keep the order of the sheet. A tie that straddles the cut-off is
    reported, because the sheet order then decides who is in."""
    ranked = sorted(teams, key=lambda t: -score[t])
    if 0 < n < len(ranked) and score[ranked[n - 1]] == score[ranked[n]]:
        warnings.warn(
            f"{label}: {ranked[n - 1]} and {ranked[n]} tie at {score[ranked[n]]} "
            f"at the cut-off for the top {n}. Sheet order decides. "
            f"Change a score to break the tie."
        )
    return ranked[:n]


def derive_sets(df: pd.DataFrame, cfg=None):
    """Build every team subset the model and the validator need, from the data."""
    cfg = {**DEFAULTS, **(cfg or {})}
    teams = df["TeamID"].tolist()
    group_of = dict(zip(df["TeamID"], df["Group"]))
    region_of = dict(zip(df["TeamID"], df["Region"]))
    score = dict(zip(df["TeamID"], pd.to_numeric(df["PopularityScore"])))

    # Popular teams: sort by PopularityScore and take the top n_popular.
    popular = _top_n(teams, score, cfg["n_popular"], "PopularityScore")

    # Revenue pair (paper rule 11): the two most popular teams (popular is
    # already sorted, highest score first).
    revenue_pair = tuple(popular[:2]) if len(popular) >= 2 else None

    # Strong teams: the teams flagged 1 in the IsStrong column.
    strong = df.loc[df["IsStrong"] == 1, "TeamID"].tolist()

    def teams_where(col, value=1):
        return df.loc[df[col] == value, "TeamID"].tolist() if col in df.columns else []

    # Rival pairs are read from both directions, so a pair listed on one row
    # only is still found.
    rivals = set()
    for team, other in zip(df["TeamID"], df["RivalTeamID"]):
        other = _clean_id(other)
        if other is not None and other != team:
            rivals.add(frozenset((team, other)))

    groups = {}
    for t in teams:
        groups.setdefault(group_of[t], []).append(t)

    return {
        "teams": teams,
        "score": score,
        "group_of": group_of,
        "region_of": region_of,
        "groups": groups,
        "popular": popular,
        "revenue_pair": revenue_pair,
        "strong": strong,
        "weak": teams_where("IsWeak"),
        "tourist": teams_where("IsTourist"),
        "rivals": rivals,
    }


# ============================================================
# 2. MODEL
# ============================================================

def build_model(df: pd.DataFrame, config=None):
    cfg = {**DEFAULTS, **(config or {})}
    validate_input(df)
    S = derive_sets(df, cfg)

    teams = S["teams"]
    group_of = S["group_of"]
    region_of = S["region_of"]
    popular = S["popular"]
    n_rounds = len(teams) - 1                      # single round-robin
    rounds = range(1, n_rounds + 1)
    last = n_rounds

    def members(region):
        return [t for t in teams if region_of[t] == region]

    prob = pulp.LpProblem("League_Scheduler", pulp.LpMaximize)

    # PuLP 3.0 and later create variables through the problem object.
    # Older versions use the LpVariable constructor.
    def new_binary(name):
        if hasattr(prob, "add_variable"):
            return prob.add_variable(name, cat="Binary")
        return pulp.LpVariable(name, cat="Binary")

    # x[i][j][k] = 1 if team i hosts team j in round k (i != j only)
    x = {
        i: {
            j: {k: new_binary(f"Match_{i}_{j}_{k}") for k in rounds}
            for j in teams if j != i
        }
        for i in teams
    }

    # ---- small helpers returning linear expressions ----
    def home(i, k):
        """1 if team i plays at home in round k."""
        return pulp.lpSum(x[i][j][k] for j in teams if j != i)

    def away(i, k):
        """1 if team i plays away in round k."""
        return pulp.lpSum(x[j][i][k] for j in teams if j != i)

    def visits(t, k, hosts):
        """1 if team t is a visitor at one of `hosts` in round k."""
        return pulp.lpSum(x[h][t][k] for h in hosts if h != t)

    def plays_in(t, k, region_teams):
        """1 if team t plays a round-k game staged in the region of `region_teams`.
        Covers visits to that region and home games of t when t belongs to it."""
        own = home(t, k) if t in region_teams else 0
        return visits(t, k, region_teams) + own

    # ============================================================
    # 3. OBJECTIVE
    # ============================================================
    # Part 1: reward games between teams of the same group in late rounds.
    # Part 2: reward tourist teams for hosting popular teams early. The reward
    # uses the popularity of both the host and the guest.

    weights = {k: w for k, w in cfg["round_weights"].items() if k in rounds}

    same_group_pairs = [
        (i, j) for i in teams for j in teams
        if i != j and group_of[i] == group_of[j]
    ]
    objective_terms = [
        w * x[i][j][k] for (i, j) in same_group_pairs for k, w in weights.items()
    ]

    score = S["score"]
    for i in S["tourist"]:
        for j in teams:
            if i != j:
                # Scores are on a 0-100 scale, so (sum / 200) is between 0 and 1.
                bonus = ((score[j] + score[i]) / 200.0) * cfg["tourist_bonus_max"]
                for k in cfg["tourist_bonus_rounds"]:
                    if k in rounds:
                        objective_terms.append(bonus * x[i][j][k])

    prob += pulp.lpSum(objective_terms)

    # ============================================================
    # 4. BASIC CONSTRAINTS (paper rules 1, 2, 3)
    # ============================================================

    # Rule 1: every pair meets exactly once.
    for a in range(len(teams)):
        for b in range(a + 1, len(teams)):
            i, j = teams[a], teams[b]
            prob += (
                pulp.lpSum(x[i][j][k] + x[j][i][k] for k in rounds) == 1,
                f"SingleRoundRobin_{i}_{j}",
            )

    # Rule 2: every team plays exactly once per round.
    for i in teams:
        for k in rounds:
            prob += home(i, k) + away(i, k) == 1, f"OneMatchPerRound_{i}_{k}"

    # Rule 3: balanced number of home games (3 or 4 for 7 rounds).
    low, high = n_rounds // 2, (n_rounds + 1) // 2
    for i in teams:
        total_home = pulp.lpSum(home(i, k) for k in rounds)
        prob += total_home >= low, f"HomeCountMin_{i}"
        prob += total_home <= high, f"HomeCountMax_{i}"

    # ============================================================
    # 5. HOME / AWAY SEQUENCES (adapts paper rules 4 and 5)
    # ============================================================
    # No run of more than `max_consecutive` home games, or away games.

    m = cfg["max_consecutive"]
    for i in teams:
        for k in range(1, n_rounds - m + 1):
            window = range(k, k + m + 1)
            prob += (
                pulp.lpSum(home(i, r) for r in window) <= m,
                f"MaxConsecutiveHome_{i}_{k}",
            )
            prob += (
                pulp.lpSum(away(i, r) for r in window) <= m,
                f"MaxConsecutiveAway_{i}_{k}",
            )

    # ============================================================
    # 6. GROUP HOME BALANCE (paper rule 7)
    # ============================================================
    # Against its group rivals a team hosts about half of them.

    for i in teams:
        rivals_in_group = [j for j in S["groups"][group_of[i]] if j != i]
        count = len(rivals_in_group)
        group_home = pulp.lpSum(x[i][j][k] for j in rivals_in_group for k in rounds)
        prob += group_home >= count // 2, f"GroupHomeMin_{i}"
        prob += group_home <= (count + 1) // 2, f"GroupHomeMax_{i}"

    # ============================================================
    # 7. GEOGRAPHIC TRAVEL RULES (paper rules 8, 9, 10)
    # ============================================================

    # Rule 8: a team of a far region (North/South) on two consecutive away games
    # may not visit the opposite far region in either game. Equivalent form: a
    # visit to the opposite region cannot be next to any other away game.
    far_a, far_b = cfg["far_regions"]
    for own, other in ((far_a, far_b), (far_b, far_a)):
        own_teams, other_teams = members(own), members(other)
        for t in own_teams:
            for k in range(1, n_rounds):
                for a, b in ((k, k + 1), (k + 1, k)):
                    prob += (
                        visits(t, a, other_teams) + away(t, b) <= 1,
                        f"NoFarTrip_{t}_{a}_{b}",
                    )

    # Rules 9 and 10: on two consecutive away games, at least one is played in
    # the team's own region. Applied to every region in the data.
    for region in sorted(set(region_of.values())):
        own_teams = members(region)
        outside = [t for t in teams if region_of[t] != region]
        for t in own_teams:
            for k in range(1, n_rounds):
                prob += (
                    visits(t, k, outside) + visits(t, k + 1, outside) <= 1,
                    f"OwnRegionTrip_{region}_{t}_{k}",
                )

    # ============================================================
    # 8. POPULAR TEAMS (paper rules 11, 12, 13, 14)
    # ============================================================

    # Rule 11: a team hosts exactly one of the two most popular teams, so it
    # is home against one and away against the other.
    if S["revenue_pair"] is not None:
        a, b = S["revenue_pair"]
        for h in teams:
            if h not in (a, b):
                prob += (
                    pulp.lpSum(x[h][a][k] + x[h][b][k] for k in rounds) == 1,
                    f"RevenueBalance_{h}",
                )

    if len(popular) >= 2:
        # Rule 12: classic matches only inside the window.
        w_start, w_end = cfg["classic_window"]
        for k in rounds:
            if k < w_start or k > w_end:
                prob += (
                    pulp.lpSum(x[i][j][k] for i in popular for j in popular if i != j) == 0,
                    f"NoClassicInRound_{k}",
                )

        # Rule 13: each popular team hosts about half of its classics
        # (exactly one when there are three popular teams).
        opponents = len(popular) - 1
        for i in popular:
            hosted = pulp.lpSum(x[i][j][k] for j in popular if j != i for k in rounds)
            prob += hosted >= opponents // 2, f"ClassicHomeMin_{i}"
            prob += hosted <= (opponents + 1) // 2, f"ClassicHomeMax_{i}"

        # Rule 14: when a popular team plays in the North (South), no other
        # popular team plays in the South (North). A popular team that is
        # hosted in, or hosts in, a region counts as playing there.
         # (disabled due to giving infeasibility in here due to less number of teams)
        # north, south = members(far_a), members(far_b)
        # for k in rounds:
        #     for p in popular:
        #         for q in popular:
        #             if p != q:
        #                 prob += (
        #                     plays_in(p, k, north) + plays_in(q, k, south) <= 1,
        #                     f"Broadcast_{p}_{q}_{k}",
        #                 )

    # ============================================================
    # 9. STRONG TEAMS (paper rule 16)
    # ============================================================
    # No weak team plays strong opponents in two consecutive rounds. (modified from all teams to only weak teams)

    strong = S["strong"]
    for i in S["weak"]:
        for k in range(1, n_rounds):
            prob += (
                pulp.lpSum(
                    x[i][j][r] + x[j][i][r]
                    for j in strong if j != i
                    for r in (k, k + 1)
                ) <= 1,
                f"NoConsecutiveStrong_{i}_{k}",
            )

    # ============================================================
    # 10. RIVALRIES (paper rule 19)
    # ============================================================

    r_start, r_end = cfg["rivalry_window"]
    r_start, r_end = max(1, r_start), min(last, r_end)
    for pair in sorted(S["rivals"], key=sorted):
        i, j = sorted(pair)
        prob += (
            pulp.lpSum(x[i][j][k] + x[j][i][k] for k in range(r_start, r_end + 1)) == 1,
            f"RivalryWindow_{i}_{j}",
        )

    # ============================================================
    # 11. INTRA-REGIONAL HOME GAMES (paper rule 25)
    # ============================================================
    # Each North (South) team hosts at least one North (South) team.

    for region in cfg["far_regions"]:
        region_teams = members(region)
        if len(region_teams) < 2:
            continue
        for i in region_teams:
            prob += (
                pulp.lpSum(x[i][j][k] for j in region_teams if j != i for k in rounds) >= 1,
                f"IntraRegionHome_{i}",
            )

    return prob, x