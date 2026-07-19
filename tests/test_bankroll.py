import math
import sys

from hypothesis import given
from hypothesis import strategies as st

from oracle.scanner.bankroll import (
    analytic_ev,
    attempts_affordable,
    bankroll_note,
    net_profit_distribution,
    prob_net_loss_after,
    prob_single_attempt_loss,
)


def test_attempts_affordable_floor() -> None:
    assert attempts_affordable(100.0, 7.0) == 14
    assert attempts_affordable(100.0, 0.0) == sys.maxsize
    assert attempts_affordable(100.0, -1.0) == sys.maxsize
    assert attempts_affordable(0.0, 5.0) == 0


def test_bankroll_note_zero_cost_says_unlimited() -> None:
    note = bankroll_note(0.0, 0.25, 500.0)
    assert "unlimited" in note
    assert "0 attempts" not in note


def test_bankroll_note_nonzero_cost_normal() -> None:
    note = bankroll_note(10.0, 0.5, 100.0)
    assert "10 attempts" in note
    assert "10.00c" in note


def test_net_profit_distribution_subtracts_attempt_cost() -> None:
    dist = net_profit_distribution([(0.5, 200.0), (0.5, 0.0)], attempt_cost=10.0)
    assert dist == [(0.5, 190.0), (0.5, -10.0)]


def test_prob_single_attempt_loss() -> None:
    dist = [(0.5, 190.0), (0.5, -10.0)]
    assert prob_single_attempt_loss(dist) == 0.5


def test_analytic_ev_hand() -> None:
    dist = [(0.5, 190.0), (0.5, -10.0)]
    assert analytic_ev(dist) == 90.0


def test_prob_net_loss_after_one_attempt_matches_single() -> None:
    dist = [(0.5, 190.0), (0.5, -10.0)]
    assert abs(prob_net_loss_after(dist, 1) - 0.5) < 1e-9


def test_prob_net_loss_after_shrinks_for_positive_ev() -> None:
    # Positive-EV bet: loss probability over many attempts should fall.
    dist = [(0.5, 190.0), (0.5, -10.0)]
    p1 = prob_net_loss_after(dist, 1)
    p5 = prob_net_loss_after(dist, 5)
    assert p5 <= p1


def test_prob_net_loss_certain_when_all_negative() -> None:
    dist = [(1.0, -10.0)]
    assert abs(prob_net_loss_after(dist, 3) - 1.0) < 1e-9


def test_analytic_ev_fair_coin() -> None:
    # Fair coin: 50% chance of 100, 50% chance of 0 → EV must be exactly 50.
    dist = [(0.5, 100.0), (0.5, 0.0)]
    assert analytic_ev(dist) == 50.0


def test_analytic_ev_degenerate() -> None:
    # Certain outcome: EV must equal the single value.
    assert analytic_ev([(1.0, 42.0)]) == 42.0


def test_analytic_ev_weighted_three_outcomes() -> None:
    # Hand-computed: 0.2*10 + 0.5*20 + 0.3*30 = 2 + 10 + 9 = 21
    dist = [(0.2, 10.0), (0.5, 20.0), (0.3, 30.0)]
    assert math.isclose(analytic_ev(dist), 21.0, rel_tol=1e-9)


@given(
    st.lists(
        st.tuples(st.floats(0.01, 1.0), st.floats(-1000.0, 1000.0)),
        min_size=1,
        max_size=6,
    )
)
def test_analytic_ev_equals_sum_p_v(pairs: list[tuple[float, float]]) -> None:
    total_p = sum(p for p, _ in pairs)
    norm = [(p / total_p, v) for p, v in pairs]  # normalize to a valid distribution
    expected = sum(p * v for p, v in norm)
    assert math.isclose(analytic_ev(norm), expected, rel_tol=1e-9, abs_tol=1e-9)
