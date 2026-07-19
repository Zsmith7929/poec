import pytest

from oracle.app import build_services

pytestmark = pytest.mark.live


def test_leagues_live() -> None:
    leagues = build_services().league.list_leagues()
    assert any(lg.ninja_available for lg in leagues)


def test_prices_currency_live() -> None:
    svc = build_services()
    default = svc.settings.default_league
    prices = svc.price.prices("Currency", default)
    assert prices
    assert all(p.chaos_value > 0 for p in prices)
