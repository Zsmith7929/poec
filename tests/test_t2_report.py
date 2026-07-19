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


def _ev(tid: str, ev_net: float, deep_link: str | None = None) -> EvRow:
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
        deep_link=deep_link,
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


_VERIFY_URL = "https://www.pathofexile.com/trade/search/InventedLeague/abc123"


def _report_with_links() -> ScanReport:
    return ScanReport(
        league="TestLeagueA",
        snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        rule_version="sha256:abc",
        rows=[_auto("big", 30.0)],
        ev_rows=[
            _ev("vaal", 90.0, deep_link=_VERIFY_URL),
            _ev("alchemy", 5.0, deep_link=None),
        ],
    )


def test_terminal_t2_deep_link_present() -> None:
    text = _report_with_links().to_terminal()
    assert _VERIFY_URL in text
    # row without deep_link shows em-dash
    lines = text.splitlines()
    alchemy_lines = [ln for ln in lines if "gamble-alchemy" in ln]
    assert alchemy_lines, "gamble-alchemy line missing from terminal output"
    assert "—" in alchemy_lines[0]


def test_markdown_t2_deep_link_present() -> None:
    md = _report_with_links().to_markdown()
    # row with deep_link renders as [open](url)
    assert f"[open]({_VERIFY_URL})" in md
    # row without deep_link renders as em-dash
    lines = md.splitlines()
    alchemy_lines = [ln for ln in lines if "gamble-alchemy" in ln]
    assert alchemy_lines, "gamble-alchemy row missing from markdown output"
    assert "—" in alchemy_lines[0]
