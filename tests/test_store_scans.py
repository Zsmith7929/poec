from datetime import UTC, datetime

from oracle.scanner.models import ScanRow
from oracle.store.db import connect
from oracle.store.scans import ScanResultRepo


def _row(tid: str, margin: float | None) -> ScanRow:
    return ScanRow(
        transform_id=tid,
        name=tid,
        input_cost=10.0,
        output_value=None if margin is None else 10.0 + margin,
        margin=margin,
        margin_pct=None if margin is None else margin / 10.0,
        liquidity=50.0,
        confidence=0.8,
        pricing_mode="auto",
        deep_link=None,
        source="ninja:x",
        ts=datetime.now(tz=UTC),
    )


def test_scan_results_table_exists(tmp_path) -> None:
    conn = connect(str(tmp_path / "t.db"))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "scan_results" in tables


def test_insert_and_recent_round_trip(tmp_path) -> None:
    repo = ScanResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("L", "sha256:abc", [_row("a", 30.0), _row("b", None)])
    recent = repo.recent("L")
    assert len(recent) == 2
    assert {r["transform_id"] for r in recent} == {"a", "b"}
    assert all(r["rule_version"] == "sha256:abc" for r in recent)


def test_append_only_accumulates(tmp_path) -> None:
    repo = ScanResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("L", "v1", [_row("a", 30.0)])
    repo.insert_many("L", "v2", [_row("a", 25.0)])
    assert len(repo.recent("L")) == 2  # nothing overwritten
