import math
from datetime import UTC, datetime

from oracle.scanner.ev import EvEngine
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import OddsTable, Outcome


class StubResolver:
    """Maps (category, key) -> ResolvedPrice; missing key -> None price."""

    def __init__(self, table: dict[tuple[str, str], ResolvedPrice]) -> None:
        self._t = table
        self.cleared = 0

    def clear_cache(self) -> None:
        self.cleared += 1

    def _lookup(self, ref: PriceRef) -> ResolvedPrice:
        return self._t.get(
            (ref.category, ref.key),
            ResolvedPrice(None, 0.0, 0.0, f"missing:{ref.category}/{ref.key}", None),
        )

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._lookup(ref)


def _p(value, liq=50.0, conf=0.8):  # type: ignore[no-untyped-def]
    return ResolvedPrice(value, liq, conf, "ninja:x", None)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _table(service_cost: float = 0.0) -> OddsTable:
    return OddsTable(
        id="t",
        name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        service_cost=service_cost,
        outcomes=[
            Outcome(result=PriceRef(category="U", key="Jackpot"), probability=0.5),
            Outcome(
                result=PriceRef(category="U", key="Brick"), probability=0.5, notes="bricked salvage"
            ),
        ],
        source="s",
        prob_sum_tolerance=1e-6,
    )


def test_ev_gross_and_net_hand_computed() -> None:
    # 0.5*200 + 0.5*0  wait -> use 0.5*200 + 0.5*20 = 110 gross
    table = _table(service_cost=5.0)
    resolver = StubResolver(
        {
            ("Currency", "Vaal Orb"): _p(3.0),
            ("U", "Jackpot"): _p(200.0),
            ("U", "Brick"): _p(20.0),
        }
    )
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row.ev_gross == 110.0  # 0.5*200 + 0.5*20
    assert row.input_cost == 3.0
    assert row.service_cost == 5.0
    assert row.ev_net == 110.0 - 3.0 - 5.0  # 102.0


def test_variance_and_stddev_hand_computed() -> None:
    table = _table()
    resolver = StubResolver(
        {
            ("Currency", "Vaal Orb"): _p(3.0),
            ("U", "Jackpot"): _p(200.0),
            ("U", "Brick"): _p(20.0),
        }
    )
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    # ev_gross = 110; var = 0.5*(200-110)^2 + 0.5*(20-110)^2 = 8100
    assert row.variance == 8100.0
    assert abs(row.stddev - math.sqrt(8100.0)) < 1e-9


def test_none_outcome_price_excluded_not_zero() -> None:
    table = _table()
    resolver = StubResolver(
        {
            ("Currency", "Vaal Orb"): _p(3.0),
            ("U", "Jackpot"): _p(200.0),
            # "Brick" missing -> None price
        }
    )
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row.unresolved_outcomes == 1
    # None excluded (not treated as 0): ev_gross = 0.5*200 = 100, NOT 100+0.
    assert row.ev_gross == 100.0
    brick = next(o for o in row.per_outcome if o.result_key == "Brick")
    assert brick.price is None
    assert brick.contribution == 0.0
    # confidence penalized because 1/2 outcomes unresolved
    assert row.confidence < 0.8


def test_liquidity_confidence_min_across_resolved_sides() -> None:
    table = _table()
    resolver = StubResolver(
        {
            ("Currency", "Vaal Orb"): _p(3.0, liq=100.0, conf=0.9),
            ("U", "Jackpot"): _p(200.0, liq=30.0, conf=0.7),
            ("U", "Brick"): _p(20.0, liq=80.0, conf=0.6),
        }
    )
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row.liquidity == 30.0  # min across sides
    assert abs(row.confidence - 0.6) < 1e-9  # min, all outcomes resolved -> no penalty


def test_evaluate_all_clears_cache_once_and_sorts_by_ev_net() -> None:
    lo = OddsTable(
        id="lo",
        name="lo",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        outcomes=[Outcome(result=PriceRef(category="U", key="A"), probability=1.0)],
        source="s",
        prob_sum_tolerance=1e-6,
    )
    hi = OddsTable(
        id="hi",
        name="hi",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        outcomes=[Outcome(result=PriceRef(category="U", key="B"), probability=1.0)],
        source="s",
        prob_sum_tolerance=1e-6,
    )
    resolver = StubResolver(
        {
            ("Currency", "Vaal Orb"): _p(3.0),
            ("U", "A"): _p(10.0),
            ("U", "B"): _p(500.0),
        }
    )
    rows = EvEngine(resolver, clock=_clock).evaluate_all([lo, hi], "TestLeagueA")
    assert resolver.cleared == 1
    assert [r.table_id for r in rows] == ["hi", "lo"]


def test_evaluate_fills_bankroll_note_when_bankroll_given() -> None:
    table = _table(service_cost=2.0)
    resolver = StubResolver(
        {
            ("Currency", "Vaal Orb"): _p(3.0),
            ("U", "Jackpot"): _p(200.0),
            ("U", "Brick"): _p(20.0),
        }
    )
    row = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA", bankroll=100.0)
    assert "affords" in row.bankroll_note
    row_none = EvEngine(resolver, clock=_clock).evaluate(table, "TestLeagueA")
    assert row_none.bankroll_note == ""
