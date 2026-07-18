import sqlite3
from datetime import UTC, datetime, timedelta


class ObservedPriceRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, league: str, spec_hash: str, chaos_value: float, ts: str) -> None:
        self._conn.execute(
            "INSERT INTO observed_prices (league, spec_hash, chaos_value, observed_ts)"
            " VALUES (?,?,?,?)",
            (league, spec_hash, chaos_value, ts),
        )
        self._conn.commit()

    def latest(self, league: str, spec_hash: str, ttl_seconds: int) -> tuple[float, str] | None:
        row = self._conn.execute(
            "SELECT chaos_value, observed_ts FROM observed_prices "
            "WHERE league=? AND spec_hash=? ORDER BY observed_ts DESC LIMIT 1",
            (league, spec_hash),
        ).fetchone()
        if row is None:
            return None
        observed = datetime.fromisoformat(row["observed_ts"])
        if datetime.now(tz=UTC) - observed > timedelta(seconds=ttl_seconds):
            return None
        return (row["chaos_value"], row["observed_ts"])
