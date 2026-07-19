from datetime import UTC, datetime
from pathlib import Path

from oracle.models import ListingQuote, Price
from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.t2_registry import load_odds_registry
from oracle.scanner.t2_service import T2Service
from oracle.store.db import connect
from oracle.store.ev_results import EvResultRepo

FIX = Path(__file__).parent / "fixtures"


class FixturePriceService:
    """Prices everything the golden fixture table references."""

    PRICES = {
        ("Currency", "Vaal Orb"): (3.0, 500),
        ("UniqueAccessory", "Golden Unique Jackpot"): (300.0, 20),
        ("UniqueAccessory", "Golden Unique NoChange"): (50.0, 30),
        ("Currency", "Vaal salvage scrap"): (1.0, 900),
    }

    def prices(self, category: str, league: str) -> list[Price]:
        now = datetime.now(tz=UTC)
        return [
            Price(
                key=key,
                league=league,
                category=category,
                chaos_value=val,
                sample_depth=depth,
                source=f"ninja:{category}",
                confidence=0.8,
                ts=now,
            )
            for (cat, key), (val, depth) in self.PRICES.items()
            if cat == category
        ]


class NullDeepLink:
    def resolve(self, spec, league):  # type: ignore[no-untyped-def]
        return ListingQuote(
            spec_hash="h",
            league=league,
            chaos_value=None,
            deep_link="https://www.pathofexile.com/trade/search/x?q=x",
            residual_instructions=[],
            source="unresolved",
            observed_ts=None,
        )


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _service(tmp_path: Path) -> T2Service:
    reg = load_odds_registry(FIX / "odds_golden", 0.01)
    resolver = PriceResolver(FixturePriceService(), NullDeepLink(), min_sample_depth=5)
    ev = EvEngine(resolver, clock=_clock)
    fac = FactoryEngine(ev, resolver, clock=_clock)
    repo = EvResultRepo(connect(str(tmp_path / "t.db")))
    return T2Service(ev, fac, reg, repo, reg.version)


def test_evaluate_returns_and_persists(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    rows = svc.evaluate("TestLeagueA")
    assert rows
    row = next(r for r in rows if r.table_id == "golden_vaal")
    # ev_gross = 0.5*300 + 0.3*50 + 0.2*1 = 150 + 15 + 0.2 = 165.2
    assert abs(row.ev_gross - 165.2) < 1e-9


def test_factory_by_id_deterministic(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    plan = svc.factory(
        "golden_vaal", "TestLeagueA", bankroll=100.0, attempts=50, seed=7, trials=2000
    )
    assert plan.table_id == "golden_vaal"
    assert plan.seed == 7
    assert plan.p10 <= plan.p50 <= plan.p90
    svc2 = _service(tmp_path)
    plan2 = svc2.factory(
        "golden_vaal", "TestLeagueA", bankroll=100.0, attempts=50, seed=7, trials=2000
    )
    assert plan.p50 == plan2.p50


def test_factory_unknown_table_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(KeyError):
        _service(tmp_path).factory(
            "nope", "TestLeagueA", bankroll=1.0, attempts=1, seed=1, trials=10
        )
