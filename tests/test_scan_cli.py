from datetime import UTC, datetime

from typer.testing import CliRunner

from oracle.cli import app
from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport

runner = CliRunner()


class FakeScanService:
    def run(self, league, min_margin=None):  # type: ignore[no-untyped-def]
        row = ScanRow(
            transform_id="big",
            name="Big Play",
            input_cost=10.0,
            output_value=75.0,
            margin=65.0,
            margin_pct=6.5,
            liquidity=40.0,
            confidence=0.8,
            pricing_mode="auto",
            deep_link=None,
            source="ninja:Fossil",
            ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        )
        report = ScanReport(
            league=league,
            snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
            rule_version="sha256:abc",
            rows=[row],
        )
        return report, None, None


class FakeServices:
    scan = FakeScanService()


def test_scan_command_prints_table(monkeypatch) -> None:
    import oracle.cli as cli

    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["scan", "--league", "InventedLeague"])
    assert result.exit_code == 0
    assert "AUTO-PRICED" in result.stdout
    assert "Big Play" in result.stdout
    assert "InventedLeague" in result.stdout


def test_scan_command_json(monkeypatch) -> None:
    import oracle.cli as cli

    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(app, ["scan", "--league", "InventedLeague", "--json"])
    assert result.exit_code == 0
    assert '"rule_version"' in result.stdout
    assert "sha256:abc" in result.stdout
