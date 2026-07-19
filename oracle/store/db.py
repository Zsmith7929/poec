import sqlite3
from pathlib import Path

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS price_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        category TEXT NOT NULL,
        key TEXT NOT NULL,
        chaos_value REAL NOT NULL,
        sample_depth INTEGER NOT NULL,
        source TEXT NOT NULL,
        confidence REAL NOT NULL,
        ts TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_price_league_cat_ts
        ON price_snapshots (league, category, ts)
    """,
    """
    CREATE TABLE IF NOT EXISTS observed_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        spec_hash TEXT NOT NULL,
        chaos_value REAL NOT NULL,
        observed_ts TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_obs_league_spec_ts
        ON observed_prices (league, spec_hash, observed_ts)
    """,
    """
    CREATE TABLE IF NOT EXISTS scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        ts TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        transform_id TEXT NOT NULL,
        name TEXT NOT NULL,
        input_cost REAL NOT NULL,
        output_value REAL,
        margin REAL,
        margin_pct REAL,
        liquidity REAL NOT NULL,
        confidence REAL NOT NULL,
        pricing_mode TEXT NOT NULL,
        source TEXT NOT NULL,
        deep_link TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_scan_league_ts
        ON scan_results (league, ts)
    """,
    """
    CREATE TABLE IF NOT EXISTS ev_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        ts TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        table_id TEXT NOT NULL,
        name TEXT NOT NULL,
        ev_gross REAL NOT NULL,
        ev_net REAL NOT NULL,
        input_cost REAL NOT NULL,
        service_cost REAL NOT NULL,
        variance REAL NOT NULL,
        stddev REAL NOT NULL,
        liquidity REAL NOT NULL,
        confidence REAL NOT NULL,
        unresolved_outcomes INTEGER NOT NULL,
        bankroll_note TEXT NOT NULL,
        source TEXT NOT NULL,
        deep_link TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_ev_league_ts
        ON ev_results (league, ts)
    """,
]


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    for ddl in MIGRATIONS:
        conn.execute(ddl)
    conn.commit()
    return conn
