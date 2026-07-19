from typer.testing import CliRunner

from oracle.cli import app
from oracle.models import League, Mod

runner = CliRunner()


class FakeServices:
    class _League:
        def list_leagues(self, realm: str = "pc") -> list[League]:
            return [League(id="TestLeagueA", realm="pc", ninja_available=True)]

    class _GameData:
        def mod_pool(self, base, ilvl, influence=None, tags=None) -> list[Mod]:
            return [
                Mod(
                    id="m1",
                    name="of Life",
                    weight=1000,
                    group="Life",
                    tags=["life"],
                    domain="item",
                    generation_type="suffix",
                    required_level=1,
                )
            ]

    league = _League()
    gamedata = _GameData()


def test_leagues_command(monkeypatch) -> None:
    import oracle.cli as cli

    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["leagues"])
    assert result.exit_code == 0
    assert "TestLeagueA" in result.stdout


def test_modpool_command(monkeypatch) -> None:
    import oracle.cli as cli

    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["modpool", "Vaal Regalia", "--ilvl", "86"])
    assert result.exit_code == 0
    assert "of Life" in result.stdout
