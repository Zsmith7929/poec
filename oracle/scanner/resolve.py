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
    demand: str = "unknown"


def _influence_set(variant: str | None) -> frozenset[str]:
    """Normalize a variant/influence into a comparable set.

    None/"" -> empty (plain base). "Shaper" -> {"shaper"}. "Crusader/Redeemer" ->
    {"crusader","redeemer"}. PriceRef.influence is a single token, so a base-type ref
    matches the stash line whose variant carries exactly that influence set.
    """
    if not variant:
        return frozenset()
    return frozenset(part.strip().lower() for part in variant.split("/") if part.strip())


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
        self._cache: dict[tuple[str, str], list[Price]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def _category_table(self, category: str, league: str) -> list[Price]:
        cache_key = (league, category)
        cached = self._cache.get(cache_key)
        if cached is None:
            cached = list(self._prices.prices(category, league))
            self._cache[cache_key] = cached
        return cached

    def _select(self, ref: PriceRef, league: str) -> Price | None:
        """Pick the price line for a ref. For base types, influence variants are
        meaningful and "no influence" means the PLAIN variant, so match on
        influence-set + ilvl. For other categories (currency, uniques) variants are not
        an influence axis, so collapse to the most-liquid line by name."""
        candidates = [p for p in self._category_table(ref.category, league) if p.key == ref.key]
        if not candidates:
            return None
        if ref.category != "BaseType":
            return max(candidates, key=lambda p: p.sample_depth)
        want = _influence_set(ref.influence)
        matches = [
            p
            for p in candidates
            if _influence_set(p.variant) == want and (ref.ilvl is None or p.ilvl == ref.ilvl)
        ]
        if not matches:
            return None
        return max(matches, key=lambda p: p.sample_depth)

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        price = self._select(ref, league)
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
            demand=price.demand,
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
