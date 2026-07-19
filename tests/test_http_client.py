import httpx
import pytest
import respx

from oracle.http.client import ComplianceError, HttpClient

UA = "oracle-test/0"
HOSTS = {"api.pathofexile.com", "poe.ninja"}


@respx.mock
def test_get_json_sends_user_agent_and_parses() -> None:
    route = respx.get("https://poe.ninja/data").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = HttpClient(UA, HOSTS)
    assert client.get_json("https://poe.ninja/data") == {"ok": True}
    assert route.calls.last.request.headers["user-agent"] == UA


def test_rejects_disallowed_host() -> None:
    client = HttpClient(UA, HOSTS)
    with pytest.raises(ComplianceError):
        client.get_json("https://www.pathofexile.com/api/trade/search")


@respx.mock
def test_retries_on_429_then_succeeds() -> None:
    respx.get("https://poe.ninja/x").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"done": 1}),
        ]
    )
    client = HttpClient(UA, HOSTS)
    assert client.get_json("https://poe.ninja/x") == {"done": 1}
