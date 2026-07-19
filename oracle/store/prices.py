import sqlite3

from oracle.models import Price


class PriceSnapshotRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    _INSERT_SQL = (
        "INSERT INTO price_snapshots "
        "(league, category, key, chaos_value, sample_depth, source, confidence, ts) "
        "VALUES (?,?,?,?,?,?,?,?)"
    )

    @staticmethod
    def _row(price: Price) -> tuple[str, str, str, float, int, str, float, str]:
        return (
            price.league,
            price.category,
            price.storage_key(),
            price.chaos_value,
            price.sample_depth,
            price.source,
            price.confidence,
            price.ts.isoformat(),
        )

    def insert(self, price: Price) -> None:
        self._conn.execute(self._INSERT_SQL, self._row(price))
        self._conn.commit()

    def insert_many(self, prices: list[Price]) -> None:
        """Batch-insert a whole feed's snapshots in one transaction. The per-row
        variant (`insert`) committed once per row, which made large stash feeds
        (~9k BaseType lines) pathologically slow."""
        if not prices:
            return
        self._conn.executemany(self._INSERT_SQL, [self._row(p) for p in prices])
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
