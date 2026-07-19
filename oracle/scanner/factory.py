import random
import statistics
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from oracle.scanner import bankroll as bankroll_math
from oracle.scanner.ev import EvEngine
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import OddsTable


class _Resolver(Protocol):
    def clear_cache(self) -> None: ...
    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice: ...
    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class FactoryPlan(BaseModel):
    table_id: str
    name: str
    attempts: int
    input_unit_cost: float
    service_cost: float
    total_input_spend: float
    expected_total_profit: float
    p10: float
    p50: float
    p90: float
    trials: int
    seed: int | None
    unresolved_outcomes: int
    bankroll: float | None
    attempts_affordable: int | None


class FactoryEngine:
    def __init__(
        self,
        ev_engine: EvEngine,
        resolver: _Resolver,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._ev = ev_engine
        self._resolver = resolver
        self._clock = clock

    def plan(
        self,
        table: OddsTable,
        league: str,
        attempts: int,
        rng: random.Random,
        trials: int,
        bankroll: float | None = None,
    ) -> FactoryPlan:
        row = self._ev.evaluate(table, league, bankroll)
        attempt_cost = row.input_cost + table.service_cost
        total_input_spend = attempts * attempt_cost

        # Resolved per-attempt net-profit outcomes (unresolved excluded, surfaced).
        resolved = [(o.probability, o.price) for o in row.per_outcome if o.price is not None]
        net = [(p, price - attempt_cost) for p, price in resolved]

        # Build cumulative distribution for sampling.
        cum: list[tuple[float, float]] = []
        acc = 0.0
        norm = sum(p for p, _ in net)
        if norm > 0.0:
            for p, value in net:
                acc += p / norm
                cum.append((acc, value))

        totals: list[float] = []
        if cum:
            for _ in range(trials):
                trial_total = 0.0
                for _ in range(attempts):
                    r = rng.random()
                    for threshold, value in cum:
                        if r <= threshold:
                            trial_total += value
                            break
                    else:
                        trial_total += cum[-1][1]
                totals.append(trial_total)
        else:
            # No resolvable outcomes: the whole spend is a surfaced loss.
            totals = [-total_input_spend] * trials

        totals_sorted = sorted(totals)
        expected = statistics.fmean(totals_sorted)

        def _pct(fraction: float) -> float:
            idx = min(len(totals_sorted) - 1, int(fraction * len(totals_sorted)))
            return totals_sorted[idx]

        affordable = (
            bankroll_math.attempts_affordable(bankroll, attempt_cost)
            if bankroll is not None
            else None
        )
        return FactoryPlan(
            table_id=table.id,
            name=table.name,
            attempts=attempts,
            input_unit_cost=row.input_cost,
            service_cost=table.service_cost,
            total_input_spend=total_input_spend,
            expected_total_profit=expected,
            p10=_pct(0.10),
            p50=_pct(0.50),
            p90=_pct(0.90),
            trials=trials,
            seed=None,
            unresolved_outcomes=row.unresolved_outcomes,
            bankroll=bankroll,
            attempts_affordable=affordable,
        )
