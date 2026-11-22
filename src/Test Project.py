# Test Project.py
# Quick checks of the validator, the rules, the objective, and the input handling.
# Run from project root:  python "src/Test Project.py"

import os
import warnings

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
        assert "Rule 8" in rules
    else:
        # Solve the unmodified model and verify the optimal schedule passes every active rule.
        prob, x = model.build_model(df)
        status, _, _ = solver.run_exact_solver(prob, msg=False)
        assert status == "Optimal"
        sched = extractor.extract_schedule(x)
        assert validator.validate_schedule(sched, df) == []

        # Rule 2: a team playing twice in the same round must be caught.
        bad_r2 = sched.copy()
        bad_r2.loc[0, "Home"] = bad_r2.loc[1, "Home"]
        probs_r2 = validator.validate_schedule(bad_r2, df)
        assert any(p.startswith("Rule 2:") for p in probs_r2)

        # Rule 12: a classic match moved outside classic_window must be caught.
        sets = model.derive_sets(df)
        popular = set(sets["popular"])
        classic_mask = sched["Home"].isin(popular) & sched["Away"].isin(popular)
        if classic_mask.any():
            bad_r12 = sched.copy()
            classic_idx = bad_r12.index[classic_mask][0]
            bad_r12.loc[classic_idx, "Round"] = 1
            probs_r12 = validator.validate_schedule(bad_r12, df)
            assert any(p.startswith("Rule 12:") for p in probs_r12)

        # Rule 19: a rivalry match moved outside rivalry_window must be caught.
        rivals = sets["rivals"]
        if rivals:
            rival_mask = sched.apply(
                lambda r: frozenset((r["Home"], r["Away"])) in rivals, axis=1
            )
            bad_r19 = sched.copy()
            rival_idx = bad_r19.index[rival_mask][0]
            bad_r19.loc[rival_idx, "Round"] = 1
            probs_r19 = validator.validate_schedule(bad_r19, df)
            assert any(p.startswith("Rule 19:") for p in probs_r19)


def test_one_sided_rival_pair_is_found():
    d = df.copy()
    d.loc[d.TeamID == "T8", "RivalTeamID"] = "None"      # only T6 lists T8
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.validate_input(d)
    assert any("One-sided rivalry" in str(w.message) for w in caught)
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
        assert "unknown team" in str(err), err
    else:
        raise AssertionError("accepted unknown rival")

    # Conflicting / chained rivals: T6 lists T3, but T3 lists T5
    d_chain = df.copy()
    d_chain.loc[d_chain.TeamID == "T8", "RivalTeamID"] = None
    d_chain.loc[d_chain.TeamID == "T6", "RivalTeamID"] = "T3"
    try:
        model.validate_input(d_chain)
    except ValueError as err:
        assert "Conflicting RivalTeamID" in str(err), err
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
        assert "Conflicting RivalTeamID" in str(err), err
    else:
        raise AssertionError("accepted two teams claiming the same rival")

    # Self-rivalry: T3 -> T3
    d_self = df.copy()
    d_self.loc[d_self.TeamID == "T5", "RivalTeamID"] = None
    d_self.loc[d_self.TeamID == "T3", "RivalTeamID"] = "T3"
    try:
        model.validate_input(d_self)
    except ValueError as err:
        assert "cannot be its own rival" in str(err), err
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
        assert "IsStrong must be 0 or 1" in str(err), err
    else:
        raise AssertionError("accepted IsStrong = 2")

    # IsWeak must also be binary
    d_weak = df.copy()
    d_weak.loc[d_weak.TeamID == "T1", "IsWeak"] = 2
    try:
        model.validate_input(d_weak)
    except ValueError as err:
        assert "IsWeak must be 0 or 1" in str(err), err
    else:
        raise AssertionError("accepted IsWeak = 2")

    # Team cannot be both strong and weak
    d_both = df.copy()
    d_both.loc[d_both.TeamID == "T4", "IsStrong"] = 1  # T4 already has IsWeak == 1
    try:
        model.validate_input(d_both)
    except ValueError as err:
        assert "both strong and weak" in str(err), err
    else:
        raise AssertionError("accepted team with both IsStrong=1 and IsWeak=1")

    # IsTourist must also be binary
    d_tour = df.copy()
    d_tour.loc[d_tour.TeamID == "T1", "IsTourist"] = 2
    try:
        model.validate_input(d_tour)
    except ValueError as err:
        assert "IsTourist must be 0 or 1" in str(err), err
    else:
        raise AssertionError("accepted IsTourist = 2")


def test_tie_at_cutoff_warns():
    d = df.copy()
    d.loc[d.TeamID == "T6", "PopularityScore"] = 85
    d.loc[d.TeamID == "T7", "PopularityScore"] = 85      # ties at the cut-off for 3rd place
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
        assert "must be a number" in str(err), err
    else:
        raise AssertionError("accepted a text score")


def test_objective_matches_original_formula():
    prob, x = model.build_model(df)
    coef = {v.name: c for v, c in prob.objective.items()}
    weights = model.DEFAULTS["round_weights"]
    max_bonus = model.DEFAULTS["tourist_bonus_max"]
    score = model.derive_sets(df)["score"]

    # Part 1: same-group games, weights 1, 15, 6 in rounds 5, 6, 7 only.
    assert coef["Match_T1_T2_5"] == weights[5] == 1
    assert coef["Match_T1_T2_6"] == weights[6] == 15
    assert coef["Match_T1_T2_7"] == weights[7] == 6
    assert "Match_T1_T2_4" not in coef

    # Part 2: tourist host bonus = (popularity host + popularity guest) / 200 * tourist_bonus_max, rounds 1 to 3.
    assert max_bonus == 6
    expected_t5_t1 = ((score["T5"] + score["T1"]) / 200.0) * max_bonus
    expected_t6_t2 = ((score["T6"] + score["T2"]) / 200.0) * max_bonus
    assert abs(coef["Match_T5_T1_1"] - expected_t5_t1) < 1e-9
    assert abs(coef["Match_T6_T2_3"] - expected_t6_t2) < 1e-9
    assert "Match_T6_T2_4" not in coef


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)