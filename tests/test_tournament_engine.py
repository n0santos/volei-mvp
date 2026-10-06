import pytest
from types import SimpleNamespace
from app.services.tournament_engine import SET_TARGETS, is_set_over, set_winner, match_points, match_result, compute_standings, mark_qualified


def test_set_targets():
    assert SET_TARGETS == {1: 15, 2: 15, 3: 18}


def test_set_not_over_at_17_17():
    assert is_set_over(17, 17, 18) is False


def test_set_over_at_19_17():
    assert is_set_over(19, 17, 18) is True


def test_set_winner_none_when_not_over():
    assert set_winner(17, 17, 18) is None


def test_set_winner_at_19_17():
    assert set_winner(19, 17, 18) == "A"


def test_set_winner_b_side():
    assert set_winner(14, 18, 18) == "B"


def test_third_set_not_over_at_14_14():
    assert is_set_over(14, 14, 15) is False


def test_third_set_not_over_at_15_14_one_point_diff():
    assert is_set_over(15, 14, 15) is False


def test_third_set_over_at_16_14():
    assert is_set_over(16, 14, 15) is True
    assert set_winner(16, 14, 15) == "A"


def test_match_points_win_2_0():
    assert match_points(2, 0) == 3


def test_match_points_win_2_1():
    assert match_points(2, 1) == 2


def test_match_points_loss_1_2():
    assert match_points(1, 2) == 1


def test_match_points_loss_0_2():
    assert match_points(0, 2) == 0


def test_match_points_invalid_combo_raises():
    with pytest.raises(ValueError):
        match_points(2, 2)


def test_match_result_finished_team_a_wins():
    result = match_result([(18, 16), (12, 18), (15, 10)])
    assert result == {
        "winner": "A",
        "sets_a": 2,
        "sets_b": 1,
        "points_a": 45,
        "points_b": 44,
    }


def test_match_result_finished_team_b_wins():
    result = match_result([(16, 18), (18, 12)])
    assert result["winner"] is None  # 1-1, not finished yet
    assert result["sets_a"] == 1
    assert result["sets_b"] == 1


def test_match_result_incomplete_returns_no_winner():
    result = match_result([(18, 16)])
    assert result["winner"] is None
    assert result["sets_a"] == 1
    assert result["sets_b"] == 0


def m(team_a, team_b, sets):
    return SimpleNamespace(team_a=team_a, team_b=team_b, sets=sets)


def test_compute_standings_orders_by_tournament_points():
    matches = [
        m("A", "B", [(18, 10), (18, 12)]),               # A wins 2-0 (A:3, B:0)
        m("A", "C", [(18, 16), (14, 18), (15, 10)]),      # A wins 2-1 (A:2, C:1)
        m("B", "C", [(18, 10), (18, 12)]),                # B wins 2-0 (B:3, C:0)
    ]
    standings = compute_standings(matches)
    order = [s["team"] for s in standings]
    assert order == ["A", "B", "C"]
    by_team = {s["team"]: s for s in standings}
    assert by_team["A"]["tournament_points"] == 5
    assert by_team["B"]["tournament_points"] == 3
    assert by_team["C"]["tournament_points"] == 1


def test_tournament_points_tie_broken_by_set_balance():
    matches = [
        m("D", "Z1", [(18, 10), (18, 10)]),   # D wins 2-0 (tp 3)
        m("D", "Z2", [(10, 18), (10, 18)]),   # D loses 0-2 (tp 0)
        m("D", "Z3", [(10, 18), (10, 18)]),   # D loses 0-2 (tp 0)
        m("E", "Z4", [(18, 10), (18, 10)]),   # E wins 2-0 (tp 3)
        m("F", "Z5", [(18, 16), (14, 18), (15, 10)]),  # F wins 2-1 (tp 2)
        m("F", "Z6", [(18, 10), (10, 18), (10, 15)]),  # F loses 1-2 (tp 1)
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["D"]["tournament_points"] == 3
    assert by_team["E"]["tournament_points"] == 3
    assert by_team["F"]["tournament_points"] == 3
    assert by_team["E"]["sets_balance"] == 2
    assert by_team["F"]["sets_balance"] == 0
    assert by_team["D"]["sets_balance"] == -2
    order = [s["team"] for s in standings if s["team"] in {"D", "E", "F"}]
    assert order == ["E", "F", "D"]


def test_tournament_points_wins_and_set_balance_tie_broken_by_wins_first():
    matches = [
        m("G", "W1", [(18, 16), (14, 18), (15, 10)]),  # G wins 2-1 (tp 2)
        m("G", "W2", [(18, 16), (14, 18), (15, 10)]),  # G wins 2-1 (tp 2)
        m("G", "W3", [(10, 18), (10, 18)]),            # G loses 0-2 (tp 0)
        m("H", "W4", [(18, 10), (18, 10)]),            # H wins 2-0 (tp 3)
        m("H", "W5", [(18, 10), (10, 18), (10, 15)]),  # H loses 1-2 (tp 1)
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["G"]["tournament_points"] == 4
    assert by_team["H"]["tournament_points"] == 4
    assert by_team["G"]["wins"] == 2
    assert by_team["H"]["wins"] == 1
    assert by_team["G"]["sets_balance"] == 0
    assert by_team["H"]["sets_balance"] == 1
    # G has worse set balance but more wins, and wins is checked first.
    order = [s["team"] for s in standings if s["team"] in {"G", "H"}]
    assert order == ["G", "H"]


def test_tournament_points_wins_and_set_balance_tie_broken_by_point_balance():
    matches = [
        m("I", "V1", [(18, 5), (18, 5)]),
        m("J", "V2", [(18, 16), (18, 16)]),
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["I"]["tournament_points"] == by_team["J"]["tournament_points"] == 3
    assert by_team["I"]["wins"] == by_team["J"]["wins"] == 1
    assert by_team["I"]["sets_balance"] == by_team["J"]["sets_balance"] == 2
    assert by_team["I"]["points_balance"] > by_team["J"]["points_balance"]
    order = [s["team"] for s in standings if s["team"] in {"I", "J"}]
    assert order == ["I", "J"]


def test_points_for_no_longer_breaks_ties():
    # Same point balance (+20) but K scored more: not a regulation criterion,
    # so with no head-to-head between them they stay tied.
    matches = [
        m("K", "V3", [(30, 20), (30, 20)]),
        m("L", "V4", [(25, 15), (25, 15)]),
    ]
    by_team = {s["team"]: s for s in compute_standings(matches)}
    assert by_team["K"]["points_balance"] == by_team["L"]["points_balance"] == 20
    assert by_team["K"]["points_for"] > by_team["L"]["points_for"]
    assert by_team["K"]["tied"] is True
    assert by_team["L"]["tied"] is True
    assert by_team["K"]["rank"] == by_team["L"]["rank"]


def level_pair_scenario():
    # X and Y end level on points (3), wins (1), set balance (0) and point
    # balance (0): each beats one team 15-10 15-10 and loses to another by
    # the same score. X also beat Y, which is what head-to-head looks at.
    # W (3 pts, +2 sets) is clearly 1st and Z (0 pts) clearly last.
    # Y is listed first so a plain stable sort would put Y ahead of X.
    return [
        m("Y", "Z", [(15, 10), (15, 10)]),
        m("X", "Y", [(15, 10), (15, 10)]),
        m("W", "X", [(15, 10), (15, 10)]),
    ]


def test_head_to_head_breaks_a_two_way_tie():
    standings = compute_standings(level_pair_scenario())

    by_team = {s["team"]: s for s in standings}
    for team in ("X", "Y"):
        assert (by_team[team]["tournament_points"], by_team[team]["wins"]) == (3, 1)
        assert (by_team[team]["sets_balance"], by_team[team]["points_balance"]) == (0, 0)
    assert [s["team"] for s in standings] == ["W", "X", "Y", "Z"]
    assert [s["rank"] for s in standings] == [1, 2, 3, 4]
    assert by_team["X"]["tied"] is False
    assert by_team["Y"]["tied"] is False


def test_two_way_tie_stays_when_the_teams_split_their_meetings():
    matches = [
        m("X", "Y", [(15, 10), (15, 10)]),
        m("Y", "X", [(15, 10), (15, 10)]),
    ]
    by_team = {s["team"]: s for s in compute_standings(matches)}
    assert by_team["X"]["tied"] is True
    assert by_team["Y"]["tied"] is True
    assert by_team["X"]["rank"] == by_team["Y"]["rank"] == 1


def test_head_to_head_does_not_apply_to_a_three_way_cycle():
    # X beats Y, Y beats Z, Z beats X, all by the same score.
    matches = [
        m("X", "Y", [(15, 10), (15, 10)]),
        m("Y", "Z", [(15, 10), (15, 10)]),
        m("Z", "X", [(15, 10), (15, 10)]),
    ]
    standings = compute_standings(matches)
    assert all(s["tied"] for s in standings)
    assert {s["rank"] for s in standings} == {1}


def test_teams_that_have_not_played_share_a_rank_but_are_not_flagged_tied():
    standings = compute_standings([], teams=["A", "B", "C"])
    assert [s["team"] for s in standings] == ["A", "B", "C"]
    assert {s["rank"] for s in standings} == {1}
    assert not any(s["tied"] for s in standings)


def test_qualification_cut_follows_head_to_head():
    # X and Y are level in every number, but X beat Y, so the cut after 2nd
    # place (W, X) is clean and Y is out - without head-to-head it would be
    # a tie at the cut and nobody would qualify.
    standings = compute_standings(level_pair_scenario())
    mark_qualified(standings)
    assert {s["team"]: s["qualified"] for s in standings} == {"W": True, "X": True, "Y": False, "Z": False}


def test_qualification_cut_is_blocked_by_an_unresolved_tie():
    matches = [
        m("W", "X", [(15, 10), (15, 10)]),
        m("W", "Y", [(15, 10), (15, 10)]),
        m("X", "Z", [(15, 10), (15, 10)]),
        m("Y", "Z", [(15, 10), (15, 10)]),
    ]  # X and Y: same record, never met
    standings = compute_standings(matches)
    mark_qualified(standings)
    assert not any(s["qualified"] for s in standings)


def test_full_tie_marks_teams_as_tied():
    matches = [
        m("M", "V5", [(18, 10), (18, 10)]),
        m("N", "V6", [(18, 10), (18, 10)]),
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["M"]["tied"] is True
    assert by_team["N"]["tied"] is True


def test_compute_standings_raises_on_unfinished_match():
    matches = [m("O", "P", [(18, 16)])]
    with pytest.raises(ValueError):
        compute_standings(matches)
