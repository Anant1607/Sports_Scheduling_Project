# src/extractor.py

import pulp
import pandas as pd


def extract_schedule(x, dummy_team="T8"):
    """
    Convert solved PuLP decision variables into a readable schedule.

    Parameters
    ----------
    x : dict
        3D dictionary of decision variables:
        x[home_team][away_team][round_num]

    dummy_team : str
        Team ID used as the dummy/bye team.

    Returns
    -------
    pd.DataFrame
        Schedule sorted by round and then home team.
    """

    # ============================================================
    # 1. INITIALIZE DATA CONTAINER
    # ============================================================

    schedule = []


    # ============================================================
    # 2. TRAVERSE ALL DECISION VARIABLES
    # ============================================================

    for home_team in x:
        for away_team in x[home_team]:
            for round_num in x[home_team][away_team]:

                # =================================================
                # 3. SAFELY EVALUATE THE SOLVER VALUE
                # =================================================

                value = pulp.value(
                    x[home_team][away_team][round_num]
                )

                # Floating-point tolerance:
                # values greater than 0.5 are treated as 1
                if value is not None and value > 0.5:

                    # =================================================
                    # 4. HANDLE DUMMY / BYE LOGIC
                    # =================================================

                    # Dummy is the home team
                    if home_team == dummy_team:

                        schedule.append({
                            "Round": round_num,
                            "Home": away_team,
                            "Away": "Bye"
                        })

                    # Dummy is the away team
                    elif away_team == dummy_team:

                        schedule.append({
                            "Round": round_num,
                            "Home": home_team,
                            "Away": "Bye"
                        })

                    # Normal fixture
                    else:

                        schedule.append({
                            "Round": round_num,
                            "Home": home_team,
                            "Away": away_team
                        })


    # ============================================================
    # 5. CONVERT TO DATAFRAME
    # ============================================================

    schedule_df = pd.DataFrame(schedule)


    # ============================================================
    # 6. SORT AND RESET INDEX
    # ============================================================

    schedule_df = (
        schedule_df
        .sort_values(
            by=["Round", "Home"]
        )
        .reset_index(drop=True)
    )


    return schedule_df
