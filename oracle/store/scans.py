import sqlite3

from oracle.scanner.models import ScanRow


class ScanResultRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_many(self, league: str, rule_version: str, rows: list[ScanRow]) -> None:
        self._conn.executemany(
            "INSERT INTO scan_results "
            "(league, ts, rule_version, transform_id, name, input_cost, output_value, "
            "margin, margin_pct, liquidity, confidence, pricing_mode, source, deep_link) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    league,
                    r.ts.isoformat(),
                    rule_version,
                    r.transform_id,
                    r.name,
                    r.input_cost,
                    r.output_value,
                    r.margin,
                    r.margin_pct,
                    r.liquidity,
                    r.confidence,
                    r.pricing_mode,
                    r.source,
                    r.deep_link,
                )
                for r in rows
            ],
        )
        self._conn.commit()

    def recent(self, league: str, limit: int = 100) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT * FROM scan_results WHERE league=? ORDER BY ts DESC, id DESC LIMIT ?",
            (league, limit),
        ).fetchall()
        return [dict(r) for r in rows]
