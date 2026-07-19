from datetime import UTC, datetime

from oracle.scanner.t2_models import EvRow
from oracle.store.db import connect
from oracle.store.ev_results import EvResultRepo


def _row(tid: str, ev_net: float) -> EvRow:
    return EvRow(
        table_id=tid,
        name=tid,
        ev_gross=ev_net + 10.0,
        ev_net=ev_net,
        input_cost=3.0,
        service_cost=2.0,
        variance=100.0,
        stddev=10.0,
        per_outcome=[],
        liquidity=40.0,
        confidence=0.8,
        bankroll_note="",
        source="ninja:x",
        deep_link=None,
        unresolved_outcomes=0,
        ts=datetime.now(tz=UTC),
    )


def test_ev_results_table_exists(tmp_path) -> None:
    conn = connect(str(tmp_path / "t.db"))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ev_results" in tables


def test_insert_and_recent_round_trip(tmp_path) -> None:
    repo = EvResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("TestLeagueA", "sha256:abc", [_row("a", 90.0), _row("b", 5.0)])
    recent = repo.recent("TestLeagueA")
    assert len(recent) == 2
    assert {r["table_id"] for r in recent} == {"a", "b"}
    assert all(r["rule_version"] == "sha256:abc" for r in recent)


def test_append_only_accumulates(tmp_path) -> None:
    repo = EvResultRepo(connect(str(tmp_path / "t.db")))
    repo.insert_many("TestLeagueA", "v1", [_row("a", 90.0)])
    repo.insert_many("TestLeagueA", "v2", [_row("a", 85.0)])
    assert len(repo.recent("TestLeagueA")) == 2
