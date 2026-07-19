import math
from collections import defaultdict

_EPS = 1e-6


def attempts_affordable(bankroll: float, attempt_cost: float) -> int:
    if attempt_cost <= 0.0:
        return 0
    return math.floor(bankroll / attempt_cost)


def net_profit_distribution(
    outcomes: list[tuple[float, float]], attempt_cost: float
) -> list[tuple[float, float]]:
    return [(p, gross - attempt_cost) for p, gross in outcomes]


def prob_single_attempt_loss(dist: list[tuple[float, float]]) -> float:
    return sum(p for p, net in dist if net < 0.0)


def analytic_ev(dist: list[tuple[float, float]]) -> float:
    return sum(p * net for p, net in dist)


def _round_key(value: float) -> float:
    return round(value / _EPS) * _EPS


def prob_net_loss_after(dist: list[tuple[float, float]], n: int) -> float:
    if n <= 0:
        return 0.0
    # Exact convolution of the discrete per-attempt net-profit distribution.
    current: dict[float, float] = {0.0: 1.0}
    for _ in range(n):
        nxt: dict[float, float] = defaultdict(float)
        for total, ptot in current.items():
            for p, net in dist:
                nxt[_round_key(total + net)] += ptot * p
        current = dict(nxt)
    return sum(prob for total, prob in current.items() if total < 0.0)


def bankroll_note(
    attempt_cost: float,
    single_loss_prob: float,
    bankroll: float | None,
) -> str:
    if bankroll is None:
        return ""
    n = attempts_affordable(bankroll, attempt_cost)
    return (
        f"bankroll {bankroll:.0f}c affords {n} attempts at {attempt_cost:.2f}c each; "
        f"P(loss per attempt)={single_loss_prob:.2f}"
    )
