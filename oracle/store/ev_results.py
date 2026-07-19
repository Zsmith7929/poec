import sqlite3

from oracle.scanner.t2_models import EvRow


class EvResultRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_many(self, league: str, rule_version: str, rows: list[EvRow]) -> None:
        self._conn.executemany(
            "INSERT INTO ev_results "
            "(league, ts, rule_version, table_id, name, ev_gross, ev_net, input_cost, "
            "service_cost, variance, stddev, liquidity, confidence, unresolved_outcomes, "
            "bankroll_note, source, deep_link) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    league,
                    r.ts.isoformat(),
                    rule_version,
                    r.table_id,
                    r.name,
                    r.ev_gross,
                    r.ev_net,
                    r.input_cost,
                    r.service_cost,
                    r.variance,
                    r.stddev,
                    r.liquidity,
                    r.confidence,
                    r.unresolved_outcomes,
                    r.bankroll_note,
                    r.source,
                    r.deep_link,
                )
                for r in rows
            ],
        )
        self._conn.commit()

    def recent(self, league: str, limit: int = 100) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT * FROM ev_results WHERE league=? ORDER BY ts DESC, id DESC LIMIT ?",
            (league, limit),
        ).fetchall()
        return [dict(r) for r in rows]
