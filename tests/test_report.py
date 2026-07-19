import json
from datetime import UTC, datetime
from pathlib import Path

from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport, write_report


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


def _verify(tid: str) -> ScanRow:
    return ScanRow(
        transform_id=tid,
        name=f"name-{tid}",
        input_cost=5.0,
        output_value=None,
        margin=None,
        margin_pct=None,
        liquidity=0.0,
        confidence=0.0,
        pricing_mode="verify",
        deep_link="https://www.pathofexile.com/trade/search/L?q=x",
        source="unresolved",
        ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
    )


def _report() -> ScanReport:
    return ScanReport(
        league="L",
        snapshot_ts=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        rule_version="sha256:abc",
        rows=[_auto("big", 30.0), _auto("small", 20.0), _verify("shield")],
    )


def test_splits_auto_and_verify_rows() -> None:
    r = _report()
    assert [x.transform_id for x in r.auto_rows()] == ["big", "small"]
    assert [x.transform_id for x in r.verify_rows()] == ["shield"]


def test_terminal_has_both_sections_and_metadata() -> None:
    text = _report().to_terminal()
    assert "AUTO-PRICED" in text
    assert "VERIFY-REQUIRED" in text
    assert "L" in text
    assert "sha256:abc" in text
    # auto ordering preserved (big before small)
    assert text.index("big") < text.index("small")


def test_markdown_embeds_metadata_and_deeplink() -> None:
    md = _report().to_markdown()
    assert "sha256:abc" in md
    assert "2026-07-18" in md
    assert "https://www.pathofexile.com/trade/search/L?q=x" in md
    assert "AUTO-PRICED" in md and "VERIFY-REQUIRED" in md


def test_json_round_trips_metadata_and_rows() -> None:
    payload = json.loads(_report().to_json())
    assert payload["league"] == "L"
    assert payload["rule_version"] == "sha256:abc"
    assert len(payload["rows"]) == 3


def test_write_report_creates_league_dir_files(tmp_path: Path) -> None:
    md_path, json_path = write_report(_report(), tmp_path)
    assert md_path.exists() and json_path.exists()
    assert md_path.parent.name == "L"
    assert md_path.name == "2026-07-18-1200.md"
    assert json_path.name == "2026-07-18-1200.json"
