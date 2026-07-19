import math
from datetime import UTC, datetime

from oracle.models import ListingQuote, Price
from oracle.scanner.ev import EvEngine
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.t2_models import OddsTable, Outcome

# --- Pinned prices for the golden temple double-corrupt hand calc. ---
# Hand calc (documented in docs/phase2-dod.md):
#   input Popular Unique copy = 40c ; service_cost = 20c
#   outcomes:
#     0.10  Jackpot      = 800c  -> 80.0
#     0.20  Good Corrupt = 150c  -> 30.0
#     0.35  No Change    =  40c  -> 14.0
#     0.35  Bricked scrap=   2c  ->  0.7
#   ev_gross = 80 + 30 + 14 + 0.7 = 124.7
#   ev_net   = 124.7 - 40 (input) - 20 (service) = 64.7
PINNED = {
    ("UniqueArmour", "Golden Popular Unique"): 40.0,
    ("UniqueArmour", "Golden Jackpot"): 800.0,
    ("UniqueArmour", "Golden Good Corrupt"): 150.0,
    ("Currency", "Golden scrap"): 2.0,
}


class PinnedPriceService:
    def prices(self, category: str, league: str) -> list[Price]:
        now = datetime.now(tz=UTC)
        return [
            Price(
                key=key,
                league=league,
                category=category,
                chaos_value=val,
                sample_depth=100,
                source=f"ninja:{category}",
                confidence=0.8,
                ts=now,
            )
            for (cat, key), val in PINNED.items()
            if cat == category
        ]


class NullDeepLink:
    def resolve(self, spec: object, league: str) -> ListingQuote:  # type: ignore[no-untyped-def]
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


def _golden_table() -> OddsTable:
    return OddsTable(
        id="golden_temple",
        name="Golden temple double-corrupt (pinned hand-calc)",
        input=PriceRef(category="UniqueArmour", key="Golden Popular Unique"),
        service_cost=20.0,
        outcomes=[
            Outcome(
                result=PriceRef(category="UniqueArmour", key="Golden Jackpot"),
                probability=0.10,
                notes="jackpot",
            ),
            Outcome(
                result=PriceRef(category="UniqueArmour", key="Golden Good Corrupt"),
                probability=0.20,
                notes="good",
            ),
            Outcome(
                result=PriceRef(category="UniqueArmour", key="Golden Popular Unique"),
                probability=0.35,
                notes="no change",
            ),
            Outcome(
                result=PriceRef(category="Currency", key="Golden scrap"),
                probability=0.35,
                notes="bricked salvage",
            ),
        ],
        source="fixture: hand-calc",
        prob_sum_tolerance=1e-9,
    )


def test_golden_temple_double_corrupt_ev_matches_hand_calc() -> None:
    resolver = PriceResolver(PinnedPriceService(), NullDeepLink(), min_sample_depth=5)
    row = EvEngine(resolver, clock=_clock).evaluate(_golden_table(), "TestLeagueA")
    assert math.isclose(row.ev_gross, 124.7, rel_tol=1e-9, abs_tol=1e-6)
    assert math.isclose(row.ev_net, 64.7, rel_tol=1e-9, abs_tol=1e-6)
    assert row.unresolved_outcomes == 0
