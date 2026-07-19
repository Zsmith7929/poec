from datetime import UTC, datetime

from oracle.models import ItemSpec, ListingQuote, Price
from oracle.scanner.models import PriceRef
from oracle.scanner.resolve import PriceResolver, ResolvedPrice


class FakePriceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def prices(self, category: str, league: str) -> list[Price]:
        self.calls.append((category, league))
        now = datetime.now(tz=UTC)
        table = {
            "Currency": [
                Price(
                    key="Chaos Orb",
                    league=league,
                    category=category,
                    chaos_value=1.0,
                    sample_depth=500,
                    source="ninja:Currency",
                    confidence=0.9,
                    ts=now,
                ),
                Price(
                    key="Divine Orb",
                    league=league,
                    category=category,
                    chaos_value=180.0,
                    sample_depth=300,
                    source="ninja:Currency",
                    confidence=0.95,
                    ts=now,
                ),
            ],
            "Fossil": [
                Price(
                    key="Bound Fossil",
                    league=league,
                    category=category,
                    chaos_value=8.0,
                    sample_depth=40,
                    source="ninja:Fossil",
                    confidence=0.7,
                    ts=now,
                )
            ],
        }
        return table.get(category, [])


class FakeResolver:
    def __init__(self, quote: ListingQuote) -> None:
        self._quote = quote
        self.seen: list[ItemSpec] = []

    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote:
        self.seen.append(spec)
        return self._quote


def _resolver(price_svc: object, quote: ListingQuote) -> PriceResolver:
    return PriceResolver(price_svc, FakeResolver(quote), min_sample_depth=5)


def _quote(value: float | None, source: str) -> ListingQuote:
    return ListingQuote(
        spec_hash="h",
        league="L",
        chaos_value=value,
        deep_link="https://www.pathofexile.com/trade/search/L?q=x",
        residual_instructions=[],
        source=source,
        observed_ts=None,
    )


def test_resolve_auto_looks_up_key_and_scales_by_qty() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    res = r.resolve_auto(PriceRef(category="Currency", key="Divine Orb", qty=2.0), "L")
    assert isinstance(res, ResolvedPrice)
    assert res.chaos_value == 360.0
    assert res.liquidity == 300
    assert res.confidence == 0.95
    assert res.source == "ninja:Currency"


def test_resolve_auto_caches_category_per_scan() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    r.resolve_auto(PriceRef(category="Currency", key="Divine Orb"), "L")
    assert svc.calls == [("Currency", "L")]  # fetched once


def test_resolve_auto_missing_key_never_fabricates() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    res = r.resolve_auto(PriceRef(category="Currency", key="Nonexistent"), "L")
    assert res.chaos_value is None
    assert res.liquidity == 0.0
    assert res.source.startswith("missing:")


def test_resolve_verify_unobserved_returns_none_with_link() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield", ilvl=84, influence="shaper")
    res = r.resolve_verify(ref, "L")
    assert res.chaos_value is None
    assert res.deep_link is not None
    assert res.source == "unresolved"


def test_resolve_verify_observed_returns_value_scaled() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(50.0, "user-observed"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield", qty=2.0)
    res = r.resolve_verify(ref, "L")
    assert res.chaos_value == 100.0
    assert res.source == "user-observed"


def test_clear_cache_forces_refetch() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    r.clear_cache()
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    assert svc.calls == [("Currency", "L"), ("Currency", "L")]
