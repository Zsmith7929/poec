from pathlib import Path

from oracle.store.db import connect


def test_connect_creates_tables(tmp_path: Path) -> None:
    conn = connect(str(tmp_path / "t.db"))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"price_snapshots", "observed_prices"} <= tables


def test_connect_is_idempotent(tmp_path: Path) -> None:
    path = str(tmp_path / "t.db")
    connect(path).close()
    conn = connect(path)  # second call must not raise
    assert conn.execute("SELECT 1").fetchone()[0] == 1
