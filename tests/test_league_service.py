import json
from pathlib import Path

from oracle.league.service import LEAGUE_API_URL, LeagueService
from oracle.models import League

FIX = Path(__file__).parent / "fixtures"


class FakeHttp:
    def get_json(self, url: str, params: dict[str, str] | None = None) -> object:
        assert url == LEAGUE_API_URL
        return json.loads((FIX / "leagues.json").read_text())


def test_list_leagues_sets_ninja_flag() -> None:
    covered = {"TestLeagueA"}
    svc = LeagueService(FakeHttp(), ninja_probe=lambda lid: lid in covered)
    leagues = svc.list_leagues()
    assert leagues == [
        League(id="TestLeagueA", realm="pc", ninja_available=True),
        League(id="TestLeagueB", realm="pc", ninja_available=False),
    ]
