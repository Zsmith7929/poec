from oracle.config import load_settings
from oracle.models import Maturity, Price
from oracle.pricing.ninja import NinjaLine
from oracle.pricing.service import PriceService
from oracle.store.db import connect


class FakeNinja:
    def currency_overview(self, league: str) -> list[NinjaLine]:
        return [NinjaLine(key="Divine Orb", chaos_value=180.0, sample_depth=42)]

    def item_overview(self, league: str, category: str) -> list[NinjaLine]:
        return [NinjaLine(key="Fossil X", chaos_value=3.0, sample_depth=15)]


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


def test_maturity_returns_model(tmp_path) -> None:
    svc = _svc(tmp_path)
    svc.prices("Currency", "TestLeagueA")
    mat = svc.maturity("TestLeagueA")
    assert isinstance(mat, Maturity)
    assert 0.0 <= mat.score <= 1.0
