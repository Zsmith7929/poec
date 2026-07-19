import sqlite3

from oracle.models import Price


class PriceSnapshotRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, price: Price) -> None:
        self._conn.execute(
            "INSERT INTO price_snapshots "
            "(league, category, key, chaos_value, sample_depth, source, confidence, ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                price.league,
                price.category,
                price.key,
                price.chaos_value,
                price.sample_depth,
                price.source,
                price.confidence,
                price.ts.isoformat(),
            ),
        )
        self._conn.commit()

    def recent_values(self, league: str, category: str, key: str, limit: int = 50) -> list[float]:
        rows = self._conn.execute(
            "SELECT chaos_value FROM price_snapshots "
            "WHERE league=? AND category=? AND key=? ORDER BY ts DESC LIMIT ?",
            (league, category, key, limit),
        ).fetchall()
        return [r["chaos_value"] for r in rows]

    def recent_depths(self, league: str, limit: int = 200) -> list[int]:
        rows = self._conn.execute(
            "SELECT sample_depth FROM price_snapshots WHERE league=? ORDER BY ts DESC LIMIT ?",
            (league, limit),
        ).fetchall()
        return [r["sample_depth"] for r in rows]
