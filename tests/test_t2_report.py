import json
from datetime import UTC, datetime

from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport
from oracle.scanner.t2_models import EvRow, OutcomeEv


def _auto(tid: str, margin: float) -> ScanRow:
    return ScanRow(
        transform_id=tid,
        name=f"name-{tid}",
        input_cost=10.0,
        output_value=10.0 + margin,
        margin=margin,
        margin_pct=margin / 10.0,
        liquidity=50.0,
        confidence=0.8,
        pricing_mode="auto",
        deep_link=None,
        source="ninja:x",
        ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
    )


def _ev(tid: str, ev_net: float) -> EvRow:
    return EvRow(
        table_id=tid,
        name=f"gamble-{tid}",
        ev_gross=ev_net + 5.0,
        ev_net=ev_net,
        input_cost=3.0,
        service_cost=2.0,
        variance=100.0,
        stddev=10.0,
        per_outcome=[
            OutcomeEv(result_key="A", probability=1.0, price=100.0, contribution=100.0, notes="")
        ],
        liquidity=40.0,
        confidence=0.7,
        bankroll_note="bankroll 100c affords 20 attempts",
        source="ninja:x",
        deep_link=None,
        unresolved_outcomes=0,
        ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
    )


def _report() -> ScanReport:
    return ScanReport(
        league="TestLeagueA",
        snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        rule_version="sha256:abc",
        rows=[_auto("big", 30.0)],
        ev_rows=[_ev("vaal", 90.0)],
    )


def test_terminal_has_separate_probabilistic_section() -> None:
    text = _report().to_terminal()
    assert "AUTO-PRICED" in text
    assert "PROBABILISTIC (Tier-2)" in text
    # deterministic section appears before probabilistic section
    assert text.index("AUTO-PRICED") < text.index("PROBABILISTIC")
    assert "gamble-vaal" in text
    assert "affords 20 attempts" in text


def test_markdown_has_probabilistic_table() -> None:
    md = _report().to_markdown()
    assert "## PROBABILISTIC (Tier-2)" in md
    assert "gamble-vaal" in md
    assert "90.00" in md  # ev_net


def test_json_includes_ev_rows() -> None:
    payload = json.loads(_report().to_json())
    assert len(payload["ev_rows"]) == 1
    assert payload["ev_rows"][0]["table_id"] == "vaal"


def test_default_ev_rows_empty_keeps_phase1_construction() -> None:
    r = ScanReport(
        league="TestLeagueA",
        snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        rule_version="v",
        rows=[_auto("x", 20.0)],
    )
    assert r.ev_rows == []
    assert "PROBABILISTIC" in r.to_terminal()  # section header present even if empty
