import random
from datetime import UTC, datetime

from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import OddsTable, Outcome


class StubResolver:
    def __init__(self, table: dict[tuple[str, str], ResolvedPrice]) -> None:
        self._t = table

    def clear_cache(self) -> None:
        pass

    def _lookup(self, ref: PriceRef) -> ResolvedPrice:
        return self._t.get(
            (ref.category, ref.key),
            ResolvedPrice(None, 0.0, 0.0, "missing", None),
        )

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)


def _p(value: float | None) -> ResolvedPrice:
    return ResolvedPrice(value, 50.0, 0.8, "ninja:x", None)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _table() -> OddsTable:
    return OddsTable(
        id="t",
        name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        service_cost=2.0,
        outcomes=[
            Outcome(result=PriceRef(category="U", key="Jackpot"), probability=0.5),
            Outcome(result=PriceRef(category="U", key="Brick"), probability=0.5),
        ],
        source="s",
        prob_sum_tolerance=1e-6,
    )


def _engine() -> tuple[FactoryEngine, StubResolver]:
    resolver = StubResolver(
        {
            ("Currency", "Vaal Orb"): _p(3.0),
            ("U", "Jackpot"): _p(200.0),
            ("U", "Brick"): _p(20.0),
        }
    )
    ev = EvEngine(resolver, clock=_clock)
    return FactoryEngine(ev, resolver, clock=_clock), resolver


def test_plan_is_deterministic_given_seed() -> None:
    eng, _ = _engine()
    p1 = eng.plan(_table(), "TestLeagueA", attempts=100, rng=random.Random(42), trials=2000)
    eng2, _ = _engine()
    p2 = eng2.plan(_table(), "TestLeagueA", attempts=100, rng=random.Random(42), trials=2000)
    assert p1.p10 == p2.p10
    assert p1.p50 == p2.p50
    assert p1.p90 == p2.p90
    assert p1.expected_total_profit == p2.expected_total_profit


def test_percentiles_ordered_and_sane() -> None:
    eng, _ = _engine()
    plan = eng.plan(_table(), "TestLeagueA", attempts=100, rng=random.Random(7), trials=5000)
    assert plan.p10 <= plan.p50 <= plan.p90
    # per-attempt net EV = 0.5*(200-5) + 0.5*(20-5) = 105; *100 attempts ≈ 10500
    assert 9000.0 < plan.expected_total_profit < 12000.0
    assert plan.total_input_spend == 100 * (3.0 + 2.0)


def test_plan_records_seed_and_trials_and_bankroll() -> None:
    eng, _ = _engine()
    plan = eng.plan(
        _table(), "TestLeagueA", attempts=10, rng=random.Random(99), trials=1000, bankroll=500.0
    )
    assert plan.trials == 1000
    assert plan.attempts == 10
    assert plan.bankroll == 500.0
    assert plan.attempts_affordable == 100  # 500 / (3+2)


def test_all_unresolved_outcomes_is_fail_visible() -> None:
    resolver = StubResolver({("Currency", "Vaal Orb"): _p(3.0)})  # outcomes missing
    eng = FactoryEngine(EvEngine(resolver, clock=_clock), resolver, clock=_clock)
    plan = eng.plan(_table(), "TestLeagueA", attempts=10, rng=random.Random(1), trials=100)
    assert plan.unresolved_outcomes == 2
    assert (
        plan.expected_total_profit == -plan.total_input_spend
    )  # no resolvable upside; loss surfaced
    assert plan.p10 == -plan.total_input_spend  # every trial is the same total loss
    assert plan.p50 == -plan.total_input_spend
    assert plan.p90 == -plan.total_input_spend
