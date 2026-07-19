from typer.testing import CliRunner

from oracle.cli import app
from oracle.config import T2Settings
from oracle.scanner.factory import FactoryPlan

runner = CliRunner()


class FakeT2:
    def factory(self, table_id, league, bankroll, attempts, seed, trials):  # type: ignore[no-untyped-def]
        return FactoryPlan(
            table_id=table_id,
            name="Fake Gamble",
            attempts=attempts,
            input_unit_cost=3.0,
            service_cost=2.0,
            total_input_spend=attempts * 5.0,
            expected_total_profit=1000.0,
            p10=200.0,
            p50=900.0,
            p90=1800.0,
            trials=trials,
            seed=seed,
            unresolved_outcomes=0,
            bankroll=bankroll,
            attempts_affordable=20,
        )


class FakeSettings:
    t2 = T2Settings(prob_sum_tolerance=0.01, default_service_cost=0.0, mc_trials=5000, mc_seed=1234)


class FakeServices:
    t2 = FakeT2()
    settings = FakeSettings()


def test_factory_command_prints_plan(monkeypatch) -> None:
    import oracle.cli as cli

    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(
        app,
        [
            "factory",
            "golden_vaal",
            "--league",
            "TestLeagueA",
            "--bankroll",
            "100",
            "--attempts",
            "50",
        ],
    )
    assert result.exit_code == 0
    assert "Fake Gamble" in result.stdout
    assert "P10" in result.stdout and "P50" in result.stdout and "P90" in result.stdout
    assert "1000.0" in result.stdout  # expected total profit


def test_factory_command_json(monkeypatch) -> None:
    import oracle.cli as cli

    monkeypatch.setattr(cli, "_services", lambda: FakeServices())
    result = runner.invoke(
        app,
        [
            "factory",
            "golden_vaal",
            "--league",
            "TestLeagueA",
            "--bankroll",
            "100",
            "--attempts",
            "50",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert '"expected_total_profit"' in result.stdout
