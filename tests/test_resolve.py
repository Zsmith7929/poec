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
            "BaseType": [
                Price(
                    key="Titanium Spirit Shield",
                    league=league,
                    category=category,
                    chaos_value=12.0,
                    sample_depth=30,
                    source="ninja:BaseType",
                    confidence=0.8,
                    ts=now,
                    variant=None,
                    ilvl=84,
                ),
                Price(
                    key="Titanium Spirit Shield",
                    league=league,
                    category=category,
                    chaos_value=250.0,
                    sample_depth=8,
                    source="ninja:BaseType",
                    confidence=0.7,
                    ts=now,
                    variant="Shaper",
                    ilvl=84,
                    demand="thin",
                ),
                Price(
                    key="Titanium Spirit Shield",
                    league=league,
                    category=category,
                    chaos_value=900.0,
                    sample_depth=50,  # deliberately the MOST liquid line
                    source="ninja:BaseType",
                    confidence=0.7,
                    ts=now,
                    variant="Crusader/Redeemer",
                    ilvl=84,
                ),
            ],
            "UniqueAccessory": [
                Price(
                    key="Watcher's Eye",
                    league=league,
                    category=category,
                    chaos_value=100.0,
                    sample_depth=3,
                    source="ninja:UniqueAccessory",
                    confidence=0.6,
                    ts=now,
                    variant="Wrath",
                    ilvl=None,
                ),
                Price(
                    key="Watcher's Eye",
                    league=league,
                    category=category,
                    chaos_value=300.0,
                    sample_depth=40,
                    source="ninja:UniqueAccessory",
                    confidence=0.8,
                    ts=now,
                    variant="Zealotry",
                    ilvl=None,
                ),
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


def test_resolve_auto_plain_base_matches_no_influence_variant() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield", ilvl=84)
    res = r.resolve_auto(ref, "L")
    assert res.chaos_value == 12.0  # plain (variant None) line, not an influenced one


def test_resolve_auto_influenced_base_matches_variant_and_ilvl() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield", influence="shaper", ilvl=84)
    res = r.resolve_auto(ref, "L")
    assert res.chaos_value == 250.0  # the Shaper ilvl-84 line specifically


def test_resolve_auto_base_no_variant_match_is_missing() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield", influence="shaper", ilvl=99)
    res = r.resolve_auto(ref, "L")
    assert res.chaos_value is None  # no Shaper at ilvl 99 -> never fabricates
    assert res.source.startswith("missing:")


def test_resolve_auto_base_no_influence_no_ilvl_matches_plain_not_most_liquid() -> None:
    # A BaseType ref with neither influence nor ilvl must resolve to the PLAIN variant,
    # never collapse to the most-liquid line (here Crusader/Redeemer at depth 50, 900c).
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield")
    res = r.resolve_auto(ref, "L")
    assert res.chaos_value == 12.0  # plain line, not the more-liquid influenced 900c one


def test_resolve_auto_propagates_demand_label() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="BaseType", key="Titanium Spirit Shield", influence="shaper", ilvl=84)
    res = r.resolve_auto(ref, "L")
    assert res.demand == "thin"  # carried from the chosen price line


def test_resolve_auto_name_only_unique_picks_most_liquid_variant() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    ref = PriceRef(category="UniqueAccessory", key="Watcher's Eye")
    res = r.resolve_auto(ref, "L")
    # name-only ref collapses variants to the most-liquid line (Zealotry, depth 40).
    assert res.chaos_value == 300.0
    assert res.liquidity == 40


def test_clear_cache_forces_refetch() -> None:
    svc = FakePriceService()
    r = _resolver(svc, _quote(None, "unresolved"))
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    r.clear_cache()
    r.resolve_auto(PriceRef(category="Currency", key="Chaos Orb"), "L")
    assert svc.calls == [("Currency", "L"), ("Currency", "L")]
