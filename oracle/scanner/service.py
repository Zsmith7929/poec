from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from oracle.scanner.engine import ScanEngine
from oracle.scanner.models import ScanRow
from oracle.scanner.report import ScanReport, write_report

if TYPE_CHECKING:
    from oracle.scanner.t2_service import T2Service


class _Repo(Protocol):
    def insert_many(self, league: str, rule_version: str, rows: list[ScanRow]) -> None: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class ScanService:
    def __init__(
        self,
        engine: ScanEngine,
        repo: _Repo,
        rule_version: str,
        reports_dir: Path,
        clock: Callable[[], datetime] = _default_clock,
        t2: T2Service | None = None,
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._rule_version = rule_version
        self._reports_dir = reports_dir
        self._clock = clock
        self._t2 = t2

    def run(self, league: str, min_margin: float | None = None) -> tuple[ScanReport, Path, Path]:
        snapshot_ts = self._clock()
        rows = self._engine.scan(league, min_margin)
        ev_rows = self._t2.evaluate(league) if self._t2 is not None else []
        report = ScanReport(
            league=league,
            snapshot_ts=snapshot_ts,
            rule_version=self._rule_version,
            rows=rows,
            ev_rows=ev_rows,
        )
        self._repo.insert_many(league, self._rule_version, rows)
        md_path, json_path = write_report(report, self._reports_dir)
        return report, md_path, json_path
