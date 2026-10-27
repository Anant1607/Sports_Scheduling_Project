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
PROJECT_ROOT = os.path.dirname(HERE)
df = pd.read_excel(os.path.join(PROJECT_ROOT, "input.xlsx"))

def test_validator_catches_known_violations():
    if "OLD_SCHEDULE" in os.environ and os.path.exists(os.environ["OLD_SCHEDULE"]):
        old = pd.read_csv(os.environ["OLD_SCHEDULE"])[["Round", "Home", "Away"]]
        problems = validator.validate_schedule(old, df)
        rules = {p.split(":")[0] for p in problems}
        print("old schedule problems:", len(problems), sorted(rules))
        assert "Rule 8" in rules and "Rule 14" in rules
    else:
        # Relax Broadcast and NoFarTrip in a test build and verify the validator catches violations
        prob, x = model.build_model(df)
        for cname in list(prob.constraints.keys()):
            if cname.startswith("Broadcast_") or cname.startswith("NoFarTrip_"):
                del prob.constraints[cname]
        status, _, _ = solver.run_exact_solver(prob, msg=False)
        assert status == "Optimal"
        sched = extractor.extract_schedule(x)
        problems = validator.validate_schedule(sched, df)
        rules = {p.split(":")[0] for p in problems}
        assert "Rule 14" in rules

        # Check that a team playing twice in the same round is caught by Rule 2
        bad_sched = sched.copy()
        bad_sched.loc[0, "Home"] = bad_sched.loc[1, "Home"]
        probs_r2 = validator.validate_schedule(bad_sched, df)
        assert any(p.startswith("Rule 2:") for p in probs_r2)


def test_one_sided_rival_pair_is_found():
    d = df.copy()
    d.loc[d.TeamID == "T8", "RivalTeamID"] = "None"      # only T6 lists T8
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.validate_input(d)
    assert any("One-sided RivalTeamID" in str(w.message) for w in caught)
    sets = model.derive_sets(d)
    assert frozenset(("T6", "T8")) in sets["rivals"]


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
    # Unknown rival team ID
    d = df.copy()
    d.loc[d.TeamID == "T7", "RivalTeamID"] = "T99"
    try:
        model.validate_input(d)
    except ValueError as err:
        assert "unknown team" in str(err)
    else:
        raise AssertionError("accepted unknown rival")

    # Conflicting / chained rivals: T6 lists T3, but T3 lists T5
    d_chain = df.copy()
    d_chain.loc[d_chain.TeamID == "T8", "RivalTeamID"] = None
    d_chain.loc[d_chain.TeamID == "T6", "RivalTeamID"] = "T3"
    try:
        model.validate_input(d_chain)
    except ValueError as err:
        assert "conflicting RivalTeamID" in str(err)
    else:
        raise AssertionError("accepted conflicting rival chain T6 -> T3 -> T5")

    # Two teams claiming the same blank rival: T6 -> T3 and T2 -> T3 while T3 is None
    d_dup = df.copy()
    d_dup.loc[d_dup.TeamID == "T8", "RivalTeamID"] = None
    d_dup.loc[d_dup.TeamID == "T5", "RivalTeamID"] = None
    d_dup.loc[d_dup.TeamID == "T3", "RivalTeamID"] = None
    d_dup.loc[d_dup.TeamID == "T6", "RivalTeamID"] = "T3"
    d_dup.loc[d_dup.TeamID == "T2", "RivalTeamID"] = "T3"
    try:
        model.validate_input(d_dup)
    except ValueError as err:
        assert "conflicting RivalTeamID" in str(err)
    else:
        raise AssertionError("accepted two teams claiming the same rival")

    # Self-rivalry: T3 -> T3
    d_self = df.copy()
    d_self.loc[d_self.TeamID == "T5", "RivalTeamID"] = None
    d_self.loc[d_self.TeamID == "T3", "RivalTeamID"] = "T3"
    try:
        model.validate_input(d_self)
    except ValueError as err:
        assert "cannot be itself" in str(err)
    else:
        raise AssertionError("accepted self rival")

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

    # Team cannot be both strong and weak
    d_both = df.copy()
    d_both.loc[d_both.TeamID == "T4", "IsStrong"] = 1  # T4 already has IsWeak == 1
    try:
        model.validate_input(d_both)
    except ValueError as err:
        assert "both strong and weak" in str(err)
    else:
        raise AssertionError("accepted team with both IsStrong=1 and IsWeak=1")

    # IsTourist must also be binary
    d_tour = df.copy()
    d_tour.loc[d_tour.TeamID == "T1", "IsTourist"] = 2
    try:
        model.validate_input(d_tour)
    except ValueError as err:
        assert "IsTourist must be 0 or 1" in str(err)
    else:
        raise AssertionError("accepted IsTourist = 2")


def test_tie_at_cutoff_warns():
    import warnings
    d = df.copy()
    d.loc[d.TeamID == "T6", "PopularityScore"] = 85
    d.loc[d.TeamID == "T7", "PopularityScore"] = 85      # ties with T6 for 3rd place
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