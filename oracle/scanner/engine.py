from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from oracle.config import ScannerSettings
from oracle.scanner.models import PriceRef, ScanRow, Transform
from oracle.scanner.registry import TransformRegistry
from oracle.scanner.resolve import ResolvedPrice


class _Resolver(Protocol):
    def clear_cache(self) -> None: ...
    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice: ...
    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice: ...


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class ScanEngine:
    def __init__(
        self,
        registry: TransformRegistry,
        resolver: _Resolver,
        settings_scanner: ScannerSettings,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._registry = registry
        self._resolver = resolver
        self._settings = settings_scanner
        self._clock = clock

    def _resolve_side(self, ref: PriceRef, is_verify: bool, league: str) -> ResolvedPrice:
        if is_verify:
            return self._resolver.resolve_verify(ref, league)
        return self._resolver.resolve_auto(ref, league)

    def _row(self, t: Transform, league: str) -> ScanRow:
        is_verify = t.pricing_mode == "verify"
        input_res = [self._resolve_side(ref, is_verify, league) for ref in t.inputs]
        output_res = self._resolve_side(t.output, is_verify, league)

        priced = [r for r in [*input_res, output_res] if r.chaos_value is not None]
        liquidity = min((r.liquidity for r in priced), default=0.0)
        confidence = min((r.confidence for r in priced), default=0.0)
        deep_link = output_res.deep_link or next(
            (r.deep_link for r in input_res if r.deep_link is not None), None
        )
        source = output_res.source

        input_cost = sum(r.chaos_value or 0.0 for r in input_res)
        inputs_priced = all(r.chaos_value is not None for r in input_res)
        output_value = output_res.chaos_value
        if output_value is None or not inputs_priced:
            margin: float | None = None
            margin_pct: float | None = None
        else:
            margin = output_value - input_cost - t.friction
            margin_pct = margin / input_cost if input_cost > 0 else None

        return ScanRow(
            transform_id=t.id,
            name=t.name,
            input_cost=input_cost,
            output_value=output_value,
            margin=margin,
            margin_pct=margin_pct,
            liquidity=liquidity,
            confidence=confidence,
            pricing_mode="verify" if is_verify else "auto",
            deep_link=deep_link,
            source=source,
            ts=self._clock(),
            # Tradeability of the sell side — a "thin" output is the mirage-margin case.
            demand=output_res.demand,
        )

    def scan(self, league: str, min_margin: float | None = None) -> list[ScanRow]:
        threshold = self._settings.min_margin if min_margin is None else min_margin
        self._resolver.clear_cache()
        rows = [self._row(t, league) for t in self._registry.enabled()]

        kept: list[ScanRow] = []
        for row in rows:
            if row.pricing_mode == "verify" or row.margin is None:
                kept.append(row)  # provisional; always retained, flagged in report
                continue
            if row.margin < threshold or row.liquidity < self._settings.min_liquidity:
                continue
            kept.append(row)

        # Priced rows (margin not None) ranked by margin desc; provisional rows last.
        kept.sort(
            key=lambda r: (r.pricing_mode == "verify" or r.margin is None, -(r.margin or 0.0))
        )
        return kept
