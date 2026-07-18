import json
from pathlib import Path

import httpx
import pytest
import respx

from oracle.http.client import HttpClient
from oracle.pricing.ninja import CURRENCY_OVERVIEW_URL, NinjaClient, NinjaSchemaError

FIX = Path(__file__).parent / "fixtures"
HOSTS = {"poe.ninja", "api.pathofexile.com"}


@respx.mock
def test_currency_overview_normalizes_lines() -> None:
    respx.get(CURRENCY_OVERVIEW_URL).mock(
        return_value=httpx.Response(
            200, json=json.loads((FIX / "ninja_currency_overview.json").read_text())
        )
    )
    client = NinjaClient(HttpClient("ua", HOSTS))
    lines = client.currency_overview("TestLeagueA")
    divine = next(x for x in lines if x.key == "Divine Orb")
    assert divine.chaos_value == 180.0
    assert divine.sample_depth == 42


@respx.mock
def test_schema_drift_fails_loud() -> None:
    respx.get(CURRENCY_OVERVIEW_URL).mock(return_value=httpx.Response(200, json={"unexpected": []}))
    client = NinjaClient(HttpClient("ua", HOSTS))
    with pytest.raises(NinjaSchemaError):
        client.currency_overview("TestLeagueA")
