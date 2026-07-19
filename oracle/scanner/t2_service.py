import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine, FactoryPlan
from oracle.scanner.t2_models import EvRow
from oracle.scanner.t2_registry import OddsRegistry


class _EvRepo(Protocol):
    def insert_many(self, league: str, rule_version: str, rows: list[EvRow]) -> None: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class T2Service:
    def __init__(
        self,
        ev_engine: EvEngine,
        factory_engine: FactoryEngine,
        registry: OddsRegistry,
        repo: _EvRepo,
        rule_version: str,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._ev = ev_engine
        self._factory = factory_engine
        self._registry = registry
        self._repo = repo
        self._rule_version = rule_version
        self._clock = clock

    def evaluate(self, league: str, bankroll: float | None = None) -> list[EvRow]:
        rows = self._ev.evaluate_all(self._registry.enabled(), league)
        self._repo.insert_many(league, self._rule_version, rows)
        return rows

    def factory(
        self,
        table_id: str,
        league: str,
        bankroll: float,
        attempts: int,
        seed: int,
        trials: int,
    ) -> FactoryPlan:
        table = next((t for t in self._registry.enabled() if t.id == table_id), None)
        if table is None:
            raise KeyError(f"unknown or disabled odds table: {table_id}")
        plan = self._factory.plan(table, league, attempts, random.Random(seed), trials, bankroll)
        return plan.model_copy(update={"seed": seed})
