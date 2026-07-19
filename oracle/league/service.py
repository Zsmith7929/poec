from collections.abc import Callable
from typing import Any, Protocol

from oracle.models import League

LEAGUE_API_URL = "https://api.pathofexile.com/leagues"


class _Http(Protocol):
    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any: ...


class LeagueService:
    def __init__(self, http: _Http, ninja_probe: Callable[[str], bool]) -> None:
        self._http = http
        self._probe = ninja_probe

    def list_leagues(self, realm: str = "pc") -> list[League]:
        payload = self._http.get_json(LEAGUE_API_URL, params={"realm": realm})
        leagues = payload["leagues"] if isinstance(payload, dict) else payload
        result: list[League] = []
        for entry in leagues:
            lid = entry["id"]
            result.append(
                League(
                    id=lid,
                    realm=entry.get("realm", realm),
                    ninja_available=self._probe(lid),
                )
            )
        return result
