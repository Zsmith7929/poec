from oracle.models import ItemSpec, ModFilter
from oracle.pricing.listings import TRADE_SITE_BASE, DeepLinkResolver


class FakeObsRepo:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, float, str]] = []

    def record(self, league: str, spec_hash: str, chaos_value: float, ts: str) -> None:
        self.rows.append((league, spec_hash, chaos_value, ts))

    def latest(self, league: str, spec_hash: str, ttl_seconds: int):
        for lg, sh, val, ts in reversed(self.rows):
            if lg == league and sh == spec_hash:
                return (val, ts)
        return None


def test_spec_hash_is_stable_and_order_independent() -> None:
    a = ItemSpec(
        base="Titanium Spirit Shield",
        ilvl=86,
        mod_filters=[ModFilter(stat_id="life"), ModFilter(stat_id="es")],
    )
    b = ItemSpec(
        base="Titanium Spirit Shield",
        ilvl=86,
        mod_filters=[ModFilter(stat_id="es"), ModFilter(stat_id="life")],
    )
    assert a.spec_hash() == b.spec_hash()


def test_resolve_builds_deeplink_without_http() -> None:
    resolver = DeepLinkResolver(FakeObsRepo(), ttl_seconds=3600)
    spec = ItemSpec(base="Titanium Spirit Shield", ilvl=86)
    quote = resolver.resolve(spec, "TestLeagueA")
    assert quote.deep_link.startswith(TRADE_SITE_BASE)
    assert "TestLeagueA" in quote.deep_link
    assert quote.chaos_value is None
    assert quote.source == "unresolved"


def test_resolve_returns_residual_instructions_for_unencodable_filters() -> None:
    resolver = DeepLinkResolver(FakeObsRepo(), ttl_seconds=3600)
    spec = ItemSpec(
        base="Titanium Spirit Shield",
        ilvl=86,
        influence="Shaper",
        mod_filters=[ModFilter(stat_id="life", min_value=None)],
    )
    quote = resolver.resolve(spec, "TestLeagueA")
    joined = " ".join(quote.residual_instructions)
    assert quote.residual_instructions
    assert "Set influence filter: Shaper" in joined
    assert "Add mod filter: life (no min value set)" in joined


def test_observed_price_round_trip_and_reuse() -> None:
    repo = FakeObsRepo()
    resolver = DeepLinkResolver(repo, ttl_seconds=3600)
    spec = ItemSpec(base="Titanium Spirit Shield", ilvl=86)
    resolver.record_observed_price(spec, "TestLeagueA", 55.0)
    quote = resolver.resolve(spec, "TestLeagueA")
    assert quote.chaos_value == 55.0
    assert quote.source == "user-observed"
    assert quote.observed_ts is not None
