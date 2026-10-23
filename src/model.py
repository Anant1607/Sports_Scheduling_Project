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

    popularity_scores = dict(zip(df["TeamID"], df["PopularityScore"]))

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
    # Only intra-group matches in rounds 5, 6 and 7
    # contribute to the objective.
    round_weights = {
        5: 1,
        6: 6,
        7: 15
    }

    for i in teams:
        for j in teams:

            # matches between same groups given weightage
            if (
                df.loc[df["TeamID"] == i, "Group"].iloc[0]
                ==
                df.loc[df["TeamID"] == j, "Group"].iloc[0]
            ):
                for k in rounds:

                    if k >= 5:
                        weight = round_weights[k]
                        objective_terms.append(
                            weight * x[i][j][k]
                        )

    # Rewards tourist teams for hosting popular teams in rounds 1,2 or 3
    for i in tourist_teams:
        for j in teams:
            if i != j:
                for k in [1, 2, 3]:
                    # Normalize the 0-100 score and apply the 10-point max weight
                    bonus = ((popularity_scores[j]+popularity_scores[i]) / 200.0) * 10
                    objective_terms.append(bonus * x[i][j][k])

    prob += pulp.lpSum(objective_terms)


    # ============================================================
    # 4. BASE CONSTRAINTS
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
    
    for i in teams:
        for k in range(1, 6):
            prob += (
                pulp.lpSum(
                    x[j][i][r]
                    for j in teams
                    if j != i
                    for r in range(k, k + 3)
                ) <= 2,
                f"NoThreeConsecutiveAway_{i}_{k}"
            )


   # ------------------------------------------------------------
    # Group Fairness
    #
    # No team plays all its group matches strictly at home or strictly away.
    # Since each team has 3 opponents in its group, it must play 
    # at least 1 and at most 2 home games against them.
    # ------------------------------------------------------------
    for i in teams:
        team_group = df.loc[
            df["TeamID"] == i, "Group"
        ].iloc[0]

        same_group_teams = (
            group_1_teams
            if team_group == 1
            else group_2_teams
        )

        # Isolate strictly HOME games against group rivals
        group_home_games = pulp.lpSum(
            x[i][j][k]
            for j in same_group_teams
            if j != i
            for k in rounds
        )

        # Must play at least 1 home game against the group (prevents all 3 away)
        prob += (
            group_home_games >= 1, 
            f"GroupFairness_MinHome_{i}"
        )

        # Must play at most 2 home games against the group (prevents all 3 at home)
        prob += (
            group_home_games <= 2, 
            f"GroupFairness_MaxHome_{i}"
        )


    # ------------------------------------------------------------
    # Regional Travel
    #
    # If a North team plays AWAY against a South team in round k,
    # it cannot play AWAY against a South team again in round k+1.
    # ------------------------------------------------------------
    #
    for i in north_teams:
        for k in range(1, 7):
    
            current_round_south_away = pulp.lpSum(
                x[j][i][k]
                for j in south_teams
            )
    
            next_round_south_away = pulp.lpSum(
                x[j][i][k + 1]
                for j in south_teams
            )
    
            prob += (
                current_round_south_away
                + next_round_south_away
                <= 1,
                f"NorthSouthTravel_{i}_{k}"
            )

    # ------------------------------------------------------------
    # Geographic Constraint (Center Teams)
    #
    # When a Center team plays two consecutive away games, 
    # at least one of the games will be played in the Center.
    # ------------------------------------------------------------
    
    # Identify Center and Non-Center teams
    center_teams = df[df["Region"] == "Center"]["TeamID"].tolist()
    non_center_teams = df[df["Region"] != "Center"]["TeamID"].tolist()

    for i in center_teams:
        # Loop through all consecutive pairs of rounds (e.g., 1&2, 2&3, etc.)
        for k in rounds[:-1]: 
            prob += (
                pulp.lpSum(
                    # x[j][i] means 'j' is home and 'i' is away
                    x[j][i][k] + x[j][i][k+1] 
                    for j in non_center_teams
                ) <= 1,
                f"Center_Geographic_Rule_{i}_Rounds_{k}_{k+1}"
            )

    # ------------------------------------------------------------
    # Geographic Constraint (North & South Teams)
    #
    # When a North (South) team plays two consecutive away games, 
    # at least one of the games will be played in the North (South).
    # ------------------------------------------------------------
    
    north_teams = df[df["Region"] == "North"]["TeamID"].tolist()
    south_teams = df[df["Region"] == "South"]["TeamID"].tolist()
    
    non_north_teams = df[df["Region"] != "North"]["TeamID"].tolist()
    non_south_teams = df[df["Region"] != "South"]["TeamID"].tolist()

    # Rule for North Teams
    for i in north_teams:
        for k in rounds[:-1]: 
            prob += (
                pulp.lpSum(
                    x[j][i][k] + x[j][i][k+1] 
                    for j in non_north_teams
                ) <= 1,
                f"North_Geographic_Rule_{i}_Rounds_{k}_{k+1}"
            )

    # Rule for South Teams
    for i in south_teams:
        for k in rounds[:-1]: 
            prob += (
                pulp.lpSum(
                    x[j][i][k] + x[j][i][k+1] 
                    for j in non_south_teams
                ) <= 1,
                f"South_Geographic_Rule_{i}_Rounds_{k}_{k+1}"
            )

    # ------------------------------------------------------------
    # Popular Teams Revenue Balance
    #
    # If a team plays at home (away) against Colo Colo (T1), 
    # it plays away (at home) against Universidad de Chile (T2).
    # ------------------------------------------------------------
    
    colo_colo = "T1"
    u_chile = "T2"
    
    for h in teams:
        # Apply only to teams that are not Colo Colo or Universidad de Chile
        if h != colo_colo and h != u_chile:
            prob += (
                pulp.lpSum(
                    # x[h][i] means 'h' is playing at home against 'i'
                    x[h][colo_colo][k] + x[h][u_chile][k]
                    for k in rounds
                ) == 1,
                f"Revenue_Balance_COLO_UCH_{h}"
            )

    # ------------------------------------------------------------
    # Classic Matchups Scheduling Window
    #
    # The three classic matchups between the popular teams (T1, T2, T3) 
    # must be played between the 3rd and 6th rounds.
    # ------------------------------------------------------------
    
    popular_teams = ["T1", "T2", "T3"]
    
    # Loop through all rounds and forbid classic matchups outside the 3-6 window
    for k in rounds:
        if k < 3 or k > 6:
            prob += (
                pulp.lpSum(
                    x[i][j][k]
                    for i in popular_teams
                    for j in popular_teams
                    if i != j
                ) == 0,
                f"No_Classic_Matchups_Round_{k}"
            )

    # ------------------------------------------------------------
    # Popular Teams Home Balance for Classics
    #
    # Each of the three popular teams (T1, T2, T3) plays exactly 
    # one classic matchup at home.
    # ------------------------------------------------------------
    
    popular_teams = ["T1", "T2", "T3"]
    
    for i in popular_teams:
        prob += (
            pulp.lpSum(
                # x[i][j] means team 'i' is hosting team 'j'
                x[i][j][k]
                for j in popular_teams 
                if j != i
                for k in rounds
            ) == 1,
            f"Exactly_One_Home_Classic_{i}"
        )

    # ------------------------------------------------------------
    # Broadcasting Constraint (Mobile Units)
    #
    # When a popular team plays in the North (South), neither of 
    # the two other popular teams can play in the South (North).
    # ------------------------------------------------------------
    
    north_teams = df[df["Region"] == "North"]["TeamID"].tolist()
    south_teams = df[df["Region"] == "South"]["TeamID"].tolist()
    popular_teams = ["T1", "T2", "T3"]

    for k in rounds:
        # Evaluate every unique pair of popular teams
        for j in popular_teams:
            for h in popular_teams:
                if j != h:
                    prob += (
                        pulp.lpSum(x[n][j][k] for n in north_teams) + 
                        pulp.lpSum(x[s][h][k] for s in south_teams) <= 1,
                        f"Broadcast_North_South_{j}_and_{h}_Round_{k}"
                    )

    # ------------------------------------------------------------
    # Strong Teams Sequencing
    #
    # No team may play two consecutive games against a strong team.
    # ------------------------------------------------------------
    
    # Identify all strong teams dynamically using the dataset column
    strong_teams = df[df["IsStrong"] == 1]["TeamID"].tolist()
    
    for i in teams:
        # Loop through all consecutive pairs of rounds (k and k+1)
        for k in rounds[:-1]:
            prob += (
                pulp.lpSum(
                    # Account for playing a strong team at home OR away in round k
                    x[i][j][k] + x[j][i][k] + 
                    # Account for playing a strong team at home OR away in round k+1
                    x[i][j][k+1] + x[j][i][k+1]
                    for j in strong_teams
                    if j != i
                ) <= 1,
                f"No_Consecutive_Strong_Teams_{i}_Rounds_{k}_{k+1}"
            )

    # ------------------------------------------------------------
    # Rivalry Match Timing (Mid-to-Late Season)
    # ------------------------------------------------------------
    for i in teams:
        rival_val = df.loc[df["TeamID"] == i, "RivalTeamID"].iloc[0]
        
        if pd.notna(rival_val) and str(rival_val).strip() != "None":
            
            rival_id = str(rival_val).strip()
            
            # Ensure we only add the constraint once per pair
            if i < rival_id:
                prob += (
                    pulp.lpSum(
                        x[i][rival_id][k] + x[rival_id][i][k]
                        for k in [4, 5, 6]
                    ) == 1,
                    f"RivalryTiming_{i}_{rival_id}"
                )

    # ------------------------------------------------------------
    # Intra-Regional Home Games
    #
    # Each North (South) team shall play at least once at home 
    # against a North (South) team.
    # ------------------------------------------------------------
    
    north_teams = df[df["Region"] == "North"]["TeamID"].tolist()
    south_teams = df[df["Region"] == "South"]["TeamID"].tolist()

    # Rule for North Teams
    for i in north_teams:
        prob += (
            pulp.lpSum(
                # x[i][j] means team 'i' hosts team 'j'
                x[i][j][k]
                for j in north_teams
                if j != i
                for k in rounds
            ) >= 1,
            f"At_Least_One_North_Home_{i}"
        )

    # Rule for South Teams
    for i in south_teams:
        prob += (
            pulp.lpSum(
                x[i][j][k]
                for j in south_teams
                if j != i
                for k in rounds
            ) >= 1,
            f"At_Least_One_South_Home_{i}"
        )

    return prob, x
