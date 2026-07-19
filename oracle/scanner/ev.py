import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from oracle.scanner import bankroll as bankroll_math
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import ResolvedPrice
from oracle.scanner.t2_models import EvRow, OddsTable, OutcomeEv


class _Resolver(Protocol):
    def clear_cache(self) -> None: ...
    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice: ...
    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class EvEngine:
    def __init__(
        self,
        resolver: _Resolver,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._resolver = resolver
        self._clock = clock

    def _resolve_ref(self, ref: PriceRef, league: str) -> ResolvedPrice:
        if ref.influence is not None or ref.ilvl is not None:
            return self._resolver.resolve_verify(ref, league)
        return self._resolver.resolve_auto(ref, league)

    def evaluate(self, table: OddsTable, league: str, bankroll: float | None = None) -> EvRow:
        resolved_input = self._resolve_ref(table.input, league)
        input_cost = resolved_input.chaos_value or 0.0

        per_outcome: list[OutcomeEv] = []
        resolved_prices: list[tuple[float, float]] = []  # (probability, price)
        liq_candidates: list[float] = []
        conf_candidates: list[float] = []
        if resolved_input.chaos_value is not None:
            liq_candidates.append(resolved_input.liquidity)
            conf_candidates.append(resolved_input.confidence)

        unresolved = 0
        deep_link = resolved_input.deep_link
        for outcome in table.outcomes:
            res = self._resolve_ref(outcome.result, league)
            if res.chaos_value is None:
                unresolved += 1
                per_outcome.append(
                    OutcomeEv(
                        result_key=outcome.result.key,
                        probability=outcome.probability,
                        price=None,
                        contribution=0.0,
                        notes=outcome.notes,
                    )
                )
                if res.deep_link is not None and deep_link is None:
                    deep_link = res.deep_link
                continue
            resolved_prices.append((outcome.probability, res.chaos_value))
            liq_candidates.append(res.liquidity)
            conf_candidates.append(res.confidence)
            per_outcome.append(
                OutcomeEv(
                    result_key=outcome.result.key,
                    probability=outcome.probability,
                    price=res.chaos_value,
                    contribution=outcome.probability * res.chaos_value,
                    notes=outcome.notes,
                )
            )

        ev_gross = sum(p * v for p, v in resolved_prices)
        ev_net = ev_gross - input_cost - table.service_cost
        variance = sum(p * (v - ev_gross) ** 2 for p, v in resolved_prices)
        stddev = math.sqrt(variance)

        liquidity = min(liq_candidates, default=0.0)
        confidence = min(conf_candidates, default=0.0)
        total = len(table.outcomes)
        if total > 0 and unresolved > 0:
            confidence *= (total - unresolved) / total

        attempt_cost = input_cost + table.service_cost
        outcome_pairs = list(resolved_prices)
        net_dist = bankroll_math.net_profit_distribution(outcome_pairs, attempt_cost)
        single_loss = bankroll_math.prob_single_attempt_loss(net_dist)
        note = bankroll_math.bankroll_note(attempt_cost, single_loss, bankroll)

        return EvRow(
            table_id=table.id,
            name=table.name,
            ev_gross=ev_gross,
            ev_net=ev_net,
            input_cost=input_cost,
            service_cost=table.service_cost,
            variance=variance,
            stddev=stddev,
            per_outcome=per_outcome,
            liquidity=liquidity,
            confidence=confidence,
            bankroll_note=note,
            source=resolved_input.source,
            deep_link=deep_link,
            unresolved_outcomes=unresolved,
            ts=self._clock(),
        )

    def evaluate_all(self, tables: list[OddsTable], league: str) -> list[EvRow]:
        self._resolver.clear_cache()
        rows = [self.evaluate(t, league) for t in tables]
        rows.sort(key=lambda r: -r.ev_net)
        return rows
