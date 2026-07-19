import json
from pathlib import Path

import httpx
import pytest
import respx

from oracle.http.client import HttpClient
from oracle.pricing.ninja import LEAGUES_URL, OVERVIEW_URL, NinjaClient, NinjaSchemaError

FIX = Path(__file__).parent / "fixtures"
HOSTS = {"poe.ninja", "api.pathofexile.com"}


@respx.mock
def test_overview_normalizes_lines() -> None:
    respx.get(OVERVIEW_URL).mock(
        return_value=httpx.Response(
            200, json=json.loads((FIX / "ninja_currency_overview.json").read_text())
        )
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    lines = client.overview("TestLeagueA", "Currency")
    divine = next(x for x in lines if x.key == "Divine Orb")
    assert divine.chaos_value == 180.0
    assert divine.sample_depth == 42


@respx.mock
def test_currency_overview_wrapper() -> None:
    """currency_overview() is a thin wrapper; ensure it still works."""
    respx.get(OVERVIEW_URL).mock(
        return_value=httpx.Response(
            200, json=json.loads((FIX / "ninja_currency_overview.json").read_text())
        )
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    lines = client.currency_overview("TestLeagueA")
    exalted = next(x for x in lines if x.key == "Exalted Orb")
    assert exalted.chaos_value == 12.5
    assert exalted.sample_depth == 300


@respx.mock
def test_item_overview_wrapper() -> None:
    """item_overview() is a thin wrapper; ensure it still works."""
    respx.get(OVERVIEW_URL).mock(
        return_value=httpx.Response(
            200, json=json.loads((FIX / "ninja_currency_overview.json").read_text())
        )
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    lines = client.item_overview("TestLeagueA", "Currency")
    assert lines


@respx.mock
def test_schema_drift_fails_loud() -> None:
    respx.get(OVERVIEW_URL).mock(return_value=httpx.Response(200, json={"unexpected": []}))
    client = NinjaClient(HttpClient("ua", HOSTS))
    with pytest.raises(NinjaSchemaError):
        client.overview("TestLeagueA", "Currency")


@respx.mock
def test_schema_drift_missing_lines_key() -> None:
    payload = {"items": [], "core": {}}
    respx.get(OVERVIEW_URL).mock(return_value=httpx.Response(200, json=payload))
    client = NinjaClient(HttpClient("ua", HOSTS))
    with pytest.raises(NinjaSchemaError, match="missing 'lines'"):
        client.overview("TestLeagueA", "Currency")


@respx.mock
def test_schema_drift_missing_items_key() -> None:
    payload = {"lines": [], "core": {}}
    respx.get(OVERVIEW_URL).mock(return_value=httpx.Response(200, json=payload))
    client = NinjaClient(HttpClient("ua", HOSTS))
    with pytest.raises(NinjaSchemaError, match="missing 'items'"):
        client.overview("TestLeagueA", "Currency")


@respx.mock
def test_schema_drift_line_missing_id() -> None:
    payload = {
        "core": {},
        "lines": [{"primaryValue": 1.0, "volumePrimaryValue": 10}],
        "items": [],
    }
    respx.get(OVERVIEW_URL).mock(return_value=httpx.Response(200, json=payload))
    client = NinjaClient(HttpClient("ua", HOSTS))
    with pytest.raises(NinjaSchemaError, match="missing 'id'"):
        client.overview("TestLeagueA", "Currency")


@respx.mock
def test_schema_drift_line_missing_primary_value() -> None:
    # poe.ninja returns sparse entries (only "id") for low-liquidity base currencies;
    # we skip them rather than crashing so thin-economy leagues still work.
    payload = {
        "core": {},
        "lines": [{"id": "chaos", "volumePrimaryValue": 10}],
        "items": [{"id": "chaos", "name": "Chaos Orb"}],
    }
    respx.get(OVERVIEW_URL).mock(return_value=httpx.Response(200, json=payload))
    client = NinjaClient(HttpClient("ua", HOSTS))
    result = client.overview("TestLeagueA", "Currency")
    assert result == []  # sparse line skipped, no crash


@respx.mock
def test_league_is_covered_true() -> None:
    respx.get(LEAGUES_URL).mock(
        return_value=httpx.Response(200, json=json.loads((FIX / "ninja_leagues.json").read_text()))
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    assert client.league_is_covered("TestLeagueA") is True


@respx.mock
def test_league_is_covered_false_absent() -> None:
    respx.get(LEAGUES_URL).mock(
        return_value=httpx.Response(200, json=json.loads((FIX / "ninja_leagues.json").read_text()))
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    assert client.league_is_covered("NotInList") is False


@respx.mock
def test_league_is_covered_false_on_error() -> None:
    respx.get(LEAGUES_URL).mock(return_value=httpx.Response(500))
    client = NinjaClient(HttpClient("ua", HOSTS, max_retries=1))
    # 500 triggers retries then raises; league_is_covered should catch and return False.
    assert client.league_is_covered("TestLeagueA") is False


@respx.mock
def test_schema_drift_line_missing_volume_primary_value() -> None:
    # Same sparse-line policy: if volumePrimaryValue is absent, skip the line.
    payload = {
        "core": {},
        "lines": [{"id": "chaos", "primaryValue": 1.0}],
        "items": [{"id": "chaos", "name": "Chaos Orb"}],
    }
    respx.get(OVERVIEW_URL).mock(return_value=httpx.Response(200, json=payload))
    client = NinjaClient(HttpClient("ua", HOSTS))
    result = client.overview("TestLeagueA", "Currency")
    assert result == []  # sparse line skipped, no crash
