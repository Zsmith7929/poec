from dataclasses import dataclass
from typing import Protocol

from oracle.models import ItemSpec, ListingQuote, Price
from oracle.scanner.models import PriceRef


class _PriceService(Protocol):
    def prices(self, category: str, league: str) -> list[Price]: ...


class _Resolver(Protocol):
    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote: ...


@dataclass(frozen=True)
class ResolvedPrice:
    chaos_value: float | None
    liquidity: float
    confidence: float
    source: str
    deep_link: str | None


class PriceResolver:
    def __init__(
        self,
        price_service: _PriceService,
        resolver: _Resolver,
        min_sample_depth: int,
    ) -> None:
        self._prices = price_service
        self._resolver = resolver
        self._min_depth = min_sample_depth
        self._cache: dict[tuple[str, str], dict[str, Price]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def _category_table(self, category: str, league: str) -> dict[str, Price]:
        cache_key = (league, category)
        cached = self._cache.get(cache_key)
        if cached is None:
            cached = {p.key: p for p in self._prices.prices(category, league)}
            self._cache[cache_key] = cached
        return cached

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        table = self._category_table(ref.category, league)
        price = table.get(ref.key)
        if price is None:
            return ResolvedPrice(
                chaos_value=None,
                liquidity=0.0,
                confidence=0.0,
                source=f"missing:{ref.category}/{ref.key}",
                deep_link=None,
            )
        return ResolvedPrice(
            chaos_value=price.chaos_value * ref.qty,
            liquidity=float(price.sample_depth),
            confidence=price.confidence,
            source=price.source,
            deep_link=None,
        )

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        spec = ItemSpec(base=ref.key, ilvl=ref.ilvl, influence=ref.influence)
        quote = self._resolver.resolve(spec, league)
        value = None if quote.chaos_value is None else quote.chaos_value * ref.qty
        liquidity = 0.0
        confidence = 0.0 if value is None else 0.5
        return ResolvedPrice(
            chaos_value=value,
            liquidity=liquidity,
            confidence=confidence,
            source=quote.source,
            deep_link=quote.deep_link,
        )
