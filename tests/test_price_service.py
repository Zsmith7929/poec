from oracle.config import load_settings
from oracle.models import Maturity, Price
from oracle.pricing.ninja import NinjaLine, StashLine
from oracle.pricing.service import PriceService
from oracle.store.db import connect


class FakeNinja:
    def currency_overview(self, league: str) -> list[NinjaLine]:
        return [NinjaLine(key="Divine Orb", chaos_value=180.0, sample_depth=42)]

    def item_overview(self, league: str, category: str) -> list[NinjaLine]:
        return [NinjaLine(key="Fossil X", chaos_value=3.0, sample_depth=15)]

    def stash_overview(self, league: str, type_: str) -> list[StashLine]:
        if type_ == "BaseType":
            return [
                StashLine(
                    key="Titanium Spirit Shield",
                    chaos_value=250.0,
                    sample_depth=8,
                    variant="Shaper",
                    ilvl=84,
                )
            ]
        # A stash line with neither variant nor ilvl (e.g. a corrupted-implicit unique).
        return [
            StashLine(key="Oni-Goroshi", chaos_value=100.0, sample_depth=5, variant=None, ilvl=None)
        ]


def _svc(tmp_path):
    settings = load_settings()
    conn = connect(str(tmp_path / "t.db"))
    return PriceService(FakeNinja(), conn, settings)


def test_prices_currency_returns_priced_and_persists(tmp_path) -> None:
    svc = _svc(tmp_path)
    prices = svc.prices("Currency", "TestLeagueA")
    assert prices and isinstance(prices[0], Price)
    divine = next(p for p in prices if p.key == "Divine Orb")
    assert divine.chaos_value == 180.0
    assert divine.source == "ninja:Currency"
    assert 0.0 <= divine.confidence <= 1.0
    # persisted
    again = svc.prices("Currency", "TestLeagueA")
    assert again[0].sample_depth >= 1


def test_prices_base_type_routes_to_stash_and_keeps_variant(tmp_path) -> None:
    svc = _svc(tmp_path)
    prices = svc.prices("BaseType", "TestLeagueA")
    assert len(prices) == 1
    p = prices[0]
    assert p.key == "Titanium Spirit Shield"
    assert p.variant == "Shaper" and p.ilvl == 84
    assert p.chaos_value == 250.0
    assert p.source == "ninja:BaseType"
    # variant-qualified storage key keeps base variants from sharing a price series.
    assert p.storage_key() == "Titanium Spirit Shield|Shaper|84"


def test_stash_price_no_variant_no_ilvl_history_round_trips(tmp_path) -> None:
    # Regression: a stash line with variant=None and ilvl=None must read history back
    # under the SAME (bare) key the write path uses — otherwise history never accumulates.
    from oracle.store.prices import PriceSnapshotRepo

    svc = _svc(tmp_path)
    svc.prices("UniqueWeapon", "TestLeagueA")
    svc.prices("UniqueWeapon", "TestLeagueA")
    conn = connect(str(tmp_path / "t.db"))
    values = PriceSnapshotRepo(conn).recent_values("TestLeagueA", "UniqueWeapon", "Oni-Goroshi")
    assert len(values) == 2  # both snapshots found under the bare key


def test_maturity_returns_model(tmp_path) -> None:
    svc = _svc(tmp_path)
    svc.prices("Currency", "TestLeagueA")
    mat = svc.maturity("TestLeagueA")
    assert isinstance(mat, Maturity)
    assert 0.0 <= mat.score <= 1.0
