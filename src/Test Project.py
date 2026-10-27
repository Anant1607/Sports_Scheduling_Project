# test_project.py
# Quick checks of the validator, the optional rules and the input handling.
# Run:  python test_project.py

import os

import pandas as pd

import extractor
import model
import solver
import validator

HERE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_excel(os.path.join(HERE, "input.xlsx"))


def test_validator_catches_known_violations():
    old = pd.read_csv(os.environ["OLD_SCHEDULE"])[["Round", "Home", "Away"]]
    problems = validator.validate_schedule(old, df)
    rules = {p.split(":")[0] for p in problems}
    print("old schedule problems:", len(problems), sorted(rules))
    assert "Rule 8" in rules and "Rule 14" in rules


def test_one_sided_rival_pair_is_found():
    d = df.copy()
    d.loc[d.TeamID == "T8", "RivalTeamID"] = "None"      # only T7 lists T8
    sets = model.derive_sets(d)
    assert frozenset(("T7", "T8")) in sets["rivals"]


def test_bad_inputs_are_rejected():
    for bad, text in (
        (df.drop(columns=["Group"]), "missing required column"),
        (df.iloc[:7], "even number"),
        (pd.concat([df, df.iloc[[0]]]), "duplicate"),
    ):
        try:
            model.validate_input(bad)
        except ValueError as err:
            assert text in str(err), err
        else:
            raise AssertionError(f"accepted bad input ({text})")
    d = df.copy()
    d.loc[d.TeamID == "T7", "RivalTeamID"] = "T99"
    try:
        model.validate_input(d)
    except ValueError as err:
        assert "unknown team" in str(err)
    else:
        raise AssertionError("accepted unknown rival")


def test_optional_rules():
    d = df.copy()
    d["CrossedTeamID"] = "None"
    d.loc[d.TeamID == "T1", "CrossedTeamID"] = "T2"
    d.loc[d.TeamID == "T8", "IsOutlying"] = 1
    d.loc[d.TeamID == "T5", "NotReadyRound1"] = 1
    prob, x = model.build_model(d)
    status, _, _ = solver.run_exact_solver(prob, msg=False)
    assert status == "Optimal", status
    sched = extractor.extract_schedule(x)
    problems = validator.validate_schedule(sched, d)
    print("optional rules problems:", problems)
    assert not problems


def test_popular_teams_come_from_sorted_scores():
    # Shuffling the rows must not change who is popular.
    shuffled = df.sample(frac=1, random_state=3).reset_index(drop=True)
    assert set(model.derive_sets(shuffled)["popular"]) == {"T1", "T2", "T3"}
    # Popular list is sorted by score, highest first, so the revenue pair is T1, T2.
    assert model.derive_sets(shuffled)["popular"] == ["T1", "T2", "T3"]
    assert model.derive_sets(shuffled)["revenue_pair"] == ("T1", "T2")
    # Changing a score changes the set: T8 becomes the most popular team.
    d = df.copy()
    d.loc[d.TeamID == "T8", "PopularityScore"] = 120
    sets = model.derive_sets(d)
    assert sets["popular"] == ["T8", "T1", "T2"], sets["popular"]
    assert sets["revenue_pair"] == ("T8", "T1")
    # n_popular is configurable.
    assert len(model.derive_sets(df, {"n_popular": 4})["popular"]) == 4


def test_strong_teams_come_from_binary_flag():
    assert set(model.derive_sets(df)["strong"]) == {"T1", "T2"}
    d = df.copy()
    d.loc[d.TeamID == "T4", "IsStrong"] = 1
    assert set(model.derive_sets(d)["strong"]) == {"T1", "T2", "T4"}
    d.loc[d.TeamID == "T4", "IsStrong"] = 2          # not binary
    try:
        model.validate_input(d)
    except ValueError as err:
        assert "IsStrong must be 0 or 1" in str(err)
    else:
        raise AssertionError("accepted IsStrong = 2")


def test_tie_at_cutoff_warns():
    import warnings
    d = df.copy()
    d.loc[d.TeamID == "T4", "PopularityScore"] = 85      # ties with T3 for 3rd place
    d.loc[d.TeamID == "T3", "PopularityScore"] = 85
    d.loc[d.TeamID == "T4", "PopularityScore"] = 85
    d.loc[d.TeamID == "T2", "PopularityScore"] = 85      # three-way tie across the cut-off
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.derive_sets(d)
    assert any("tie" in str(w.message) for w in caught)


def test_non_numeric_score_is_rejected():
    d = df.copy()
    d["PopularityScore"] = d["PopularityScore"].astype(object)
    d.loc[0, "PopularityScore"] = "high"
    try:
        model.validate_input(d)
    except ValueError as err:
        assert "must be a number" in str(err)
    else:
        raise AssertionError("accepted a text score")


def test_objective_matches_original_formula():
    prob, x = model.build_model(df)
    coef = {v.name: c for v, c in prob.objective.items()}
    # Part 1: same-group games, weights 1, 6, 15 in rounds 5, 6, 7 only.
    assert coef["Match_T1_T2_5"] == 1
    assert coef["Match_T1_T2_6"] == 6
    assert coef["Match_T1_T2_7"] == 15
    assert "Match_T1_T2_4" not in coef
    # Part 2: tourist host bonus = (popularity host + popularity guest) / 200 x 10, rounds 1 to 3.
    assert abs(coef["Match_T5_T1_1"] - (45 + 100) / 200 * 10) < 1e-9     # 7.25
    assert abs(coef["Match_T6_T2_3"] - (35 + 95) / 200 * 10) < 1e-9      # 6.5
    assert "Match_T6_T2_4" not in coef


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)