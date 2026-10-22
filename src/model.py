# src/model.py

import pulp
import pandas as pd


# ============================================================
# 1. DATA INGESTION AND SET CREATION
# ============================================================

def build_model(df: pd.DataFrame):

    # -------------------------
    # Primary sets
    # -------------------------
    teams = df["TeamID"].tolist()
    rounds = range(1, 8)

    # -------------------------
    # Subsets
    # -------------------------
    group_1_teams = df[df["Group"] == 1]["TeamID"].tolist()
    group_2_teams = df[df["Group"] == 2]["TeamID"].tolist()

    popular_teams = df[df["IsPopular"] == 1]["TeamID"].tolist()
    north_teams = df[df["Region"] == "North"]["TeamID"].tolist()
    south_teams = df[df["Region"] == "South"]["TeamID"].tolist()
    center_teams = df[df["Region"] == "Center"]["TeamID"].tolist()

    tourist_teams = df[df["IsTourist"] == 1]["TeamID"].tolist()
    strong_teams = df[df["IsStrong"] == 1]["TeamID"].tolist()
    weak_teams = df[df["IsWeak"] == 1]["TeamID"].tolist()


    # ============================================================
    # 2. MODEL AND VARIABLE INITIALIZATION
    # ============================================================

    prob = pulp.LpProblem(
        "Chilean_League_Scheduler",
        pulp.LpMaximize
    )

    # x[i][j][k] = 1 if team i hosts team j in round k
    x = {
        i: {
            j: {
                k: prob.add_variable(f"Match_{i}_{j}_{k}", cat="Binary")
                for k in rounds
            }
            for j in teams
        }
        for i in teams
    }


    # ============================================================
    # 3. OBJECTIVE FUNCTION
    # ============================================================

    objective_terms = []

    # Weight later rounds more heavily.
    # Only inter-group matches in rounds 5, 6 and 7
    # contribute to the objective.
    round_weights = {
        5: 1,
        6: 6,
        7: 15
    }

    for i in teams:
        for j in teams:

            # Only matches between different groups
            if (
                df.loc[df["TeamID"] == i, "Group"].iloc[0]
                !=
                df.loc[df["TeamID"] == j, "Group"].iloc[0]
            ):
                for k in rounds:

                    if k >= 5:
                        weight = round_weights[k]
                        objective_terms.append(
                            weight * x[i][j][k]
                        )

    prob += pulp.lpSum(objective_terms)


    # ============================================================
    # 4. BASE CONSTRAINTS (PHASE 1)
    # ============================================================

    # ------------------------------------------------------------
    # No Self-Play
    # ------------------------------------------------------------
    for i in teams:
        for k in rounds:
            prob += (
                x[i][i][k] == 0,
                f"NoSelfPlay_{i}_{k}"
            )


    # ------------------------------------------------------------
    # Single Round-Robin
    #
    # Every pair of distinct teams plays exactly once.
    #
    # x[i][j][k] = i hosts j
    # x[j][i][k] = j hosts i
    # ------------------------------------------------------------
    for i in teams:
        for j in teams:

            if i < j:
                prob += (
                    pulp.lpSum(
                        x[i][j][k] + x[j][i][k]
                        for k in rounds
                    ) == 1,
                    f"SingleRoundRobin_{i}_{j}"
                )


    # ------------------------------------------------------------
    # One Match Per Round
    #
    # Each team must play exactly one match in every round.
    # ------------------------------------------------------------
    for i in teams:
        for k in rounds:

            prob += (
                pulp.lpSum(
                    x[i][j][k] + x[j][i][k]
                    for j in teams
                    if j != i
                ) == 1,
                f"OneMatchPerRound_{i}_{k}"
            )


    # ============================================================
    # 5. ADVANCED CONSTRAINTS (PHASE 3)
    #
    # Uncomment these one at a time during testing.
    # ============================================================

    # ------------------------------------------------------------
    # Home/Away Balance
    #
    # Prevents 3 consecutive home games.
    # ------------------------------------------------------------
    #
    for i in teams:
        for k in range(1, 6):
            prob += (
                pulp.lpSum(
                    x[i][j][r]
                    for j in teams
                    if j != i
                    for r in range(k, k + 3)
                ) <= 2,
                f"NoThreeConsecutiveHome_{i}_{k}"
            )


    # ------------------------------------------------------------
    # Away Balance
    #
    # Prevents 3 consecutive away games.
    # ------------------------------------------------------------
    #
    # for i in teams:
    #     for k in range(1, 6):
    #         prob += (
    #             pulp.lpSum(
    #                 x[j][i][r]
    #                 for j in teams
    #                 if j != i
    #                 for r in range(k, k + 3)
    #             ) <= 2,
    #             f"NoThreeConsecutiveAway_{i}_{k}"
    #         )


    # ------------------------------------------------------------
    # Group Fairness
    #
    # Each team must play exactly 2 opponents from its own group.
    # ------------------------------------------------------------
    #
    # for i in teams:
    #     team_group = df.loc[
    #         df["TeamID"] == i, "Group"
    #     ].iloc[0]
    #
    #     same_group_teams = (
    #         group_1_teams
    #         if team_group == 1
    #         else group_2_teams
    #     )
    #
    #     prob += (
    #         pulp.lpSum(
    #             x[i][j][k] + x[j][i][k]
    #             for j in same_group_teams
    #             if j != i
    #             for k in rounds
    #         ) == 2,
    #         f"GroupFairness_{i}"
    #     )


    # ------------------------------------------------------------
    # Regional Travel
    #
    # If a North team plays AWAY against a South team in round k,
    # it cannot play AWAY against a South team again in round k+1.
    # ------------------------------------------------------------
    #
    # for i in north_teams:
    #     for k in range(1, 7):
    #
    #         current_round_south_away = pulp.lpSum(
    #             x[j][i][k]
    #             for j in south_teams
    #         )
    #
    #         next_round_south_away = pulp.lpSum(
    #             x[j][i][k + 1]
    #             for j in south_teams
    #         )
    #
    #         prob += (
    #             current_round_south_away
    #             + next_round_south_away
    #             <= 1,
    #             f"NorthSouthTravel_{i}_{k}"
    #         )


    # ------------------------------------------------------------
    # Tourist Rule
    #
    # Every tourist team must host at least one popular team
    # during rounds 1 or 2.
    # ------------------------------------------------------------
    #
    # for i in tourist_teams:
    #     prob += (
    #         pulp.lpSum(
    #             x[i][j][k]
    #             for j in popular_teams
    #             for k in [1, 2]
    #             if j != i
    #         ) >= 1,
    #         f"TouristRule_{i}"
    #     )


    # ============================================================
    # RETURN MODEL AND VARIABLES
    # ============================================================

    return prob, x
