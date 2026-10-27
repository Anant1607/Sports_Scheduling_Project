# extractor.py

import pandas as pd
import pulp

COLUMNS = ["Round", "Home", "Away"]


def extract_schedule(x, dummy_team=None):
    """
    Convert solved PuLP decision variables into a readable schedule.

    Parameters
    ----------
    x : dict
        x[home_team][away_team][round_num] holds a binary variable.

    dummy_team : str or None
        Team ID used as a dummy/bye team. Leave as None unless the model
        really contains a dummy team. With an even number of real teams there
        is none.

    Returns
    -------
    pd.DataFrame
        Columns Round, Home, Away, sorted by round and then home team.
    """
    rows = []

    for home_team, by_away in x.items():
        for away_team, by_round in by_away.items():
            for round_num, var in by_round.items():
                value = pulp.value(var)

                # Binary values can come back as 0.9999999, so use a threshold.
                if value is None or value <= 0.5:
                    continue

                if dummy_team is not None and home_team == dummy_team:
                    rows.append({"Round": round_num, "Home": away_team, "Away": "Bye"})
                elif dummy_team is not None and away_team == dummy_team:
                    rows.append({"Round": round_num, "Home": home_team, "Away": "Bye"})
                else:
                    rows.append({"Round": round_num, "Home": home_team, "Away": away_team})

    schedule_df = pd.DataFrame(rows, columns=COLUMNS)
    return schedule_df.sort_values(by=["Round", "Home"]).reset_index(drop=True)