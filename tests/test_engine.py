from datetime import UTC, datetime

from oracle.config import ScannerSettings
from oracle.scanner.engine import ScanEngine
from oracle.scanner.models import PriceRef, Transform
from oracle.scanner.registry import TransformRegistry
from oracle.scanner.resolve import ResolvedPrice


class StubResolver:
    """Maps (category, key) -> ResolvedPrice for auto; a fixed quote for verify."""

    def __init__(self, auto: dict[tuple[str, str], ResolvedPrice], verify: ResolvedPrice) -> None:
        self._auto = auto
        self._verify = verify

    def clear_cache(self) -> None:
        pass

    def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._auto[(ref.category, ref.key)]

    def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
        return self._verify


def _auto(value: float, liq: float, conf: float) -> ResolvedPrice:
    return ResolvedPrice(
        chaos_value=value, liquidity=liq, confidence=conf, source="ninja:x", deep_link=None
    )


def _settings() -> ScannerSettings:
    return ScannerSettings(min_margin=15.0, min_liquidity=5.0)


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _t(
    tid: str,
    in_cat: str,
    in_key: str,
    out_cat: str,
    out_key: str,
    friction: float = 0.0,
    mode: str = "auto",
) -> Transform:
    return Transform(
        id=tid,
        name=tid,
        inputs=[PriceRef(category=in_cat, key=in_key)],
        output=PriceRef(category=out_cat, key=out_key),
        friction=friction,
        pricing_mode=mode,
    )  # type: ignore[arg-type]


def test_margin_math_and_pct() -> None:
    t = _t("big", "Currency", "Chaos Orb", "Fossil", "Bound Fossil", friction=1.0)
    auto = {
        ("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
        ("Fossil", "Bound Fossil"): _auto(40.0, 50, 0.8),
    }
    engine = ScanEngine(
        TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)), _settings(), clock=_clock
    )
    rows = engine.scan("L")
    assert len(rows) == 1
    row = rows[0]
    assert row.input_cost == 10.0
    assert row.output_value == 40.0
    assert row.margin == 29.0  # 40 - 10 - 1
    assert abs(row.margin_pct - 2.9) < 1e-9
    assert row.liquidity == 50  # min across sides
    assert row.confidence == 0.8


def test_ranking_descending_by_margin() -> None:
    t1 = _t("small", "Currency", "Chaos Orb", "Fossil", "A")
    t2 = _t("large", "Currency", "Chaos Orb", "Fossil", "B")
    auto = {
        ("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
        ("Fossil", "A"): _auto(30.0, 50, 0.8),
        ("Fossil", "B"): _auto(80.0, 50, 0.8),
    }
    engine = ScanEngine(
        TransformRegistry([t1, t2], "v"),
        StubResolver(auto, _auto(0, 0, 0)),
        _settings(),
        clock=_clock,
    )
    rows = engine.scan("L")
    assert [r.transform_id for r in rows] == ["large", "small"]


def test_below_min_margin_suppressed() -> None:
    t = _t("thin", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {
        ("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
        ("Fossil", "A"): _auto(20.0, 50, 0.8),
    }  # margin 10 < 15
    engine = ScanEngine(
        TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)), _settings(), clock=_clock
    )
    assert engine.scan("L") == []


def test_below_min_liquidity_suppressed() -> None:
    t = _t("illiquid", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {
        ("Currency", "Chaos Orb"): _auto(10.0, 2, 0.9),  # liq 2 < 5
        ("Fossil", "A"): _auto(80.0, 2, 0.8),
    }
    engine = ScanEngine(
        TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)), _settings(), clock=_clock
    )
    assert engine.scan("L") == []


def test_verify_row_retained_and_flagged_with_deeplink() -> None:
    t = _t("shield", "BaseType", "Plain Base", "BaseType", "Shaper Base", mode="verify")
    auto = {("BaseType", "Plain Base"): _auto(5.0, 40, 0.7)}
    verify = ResolvedPrice(
        chaos_value=None,
        liquidity=0.0,
        confidence=0.0,
        source="unresolved",
        deep_link="https://www.pathofexile.com/trade/search/L?q=x",
    )
    engine = ScanEngine(
        TransformRegistry([t], "v"), StubResolver(auto, verify), _settings(), clock=_clock
    )
    rows = engine.scan("L")
    assert len(rows) == 1
    assert rows[0].pricing_mode == "verify"
    assert rows[0].output_value is None
    assert rows[0].margin is None
    assert rows[0].deep_link is not None


def test_priced_rows_rank_before_provisional_verify_rows() -> None:
    priced = _t("priced", "Currency", "Chaos Orb", "Fossil", "A")
    prov = _t("prov", "BaseType", "Plain Base", "BaseType", "Shaper Base", mode="verify")
    auto = {
        ("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
        ("Fossil", "A"): _auto(80.0, 50, 0.8),
        ("BaseType", "Plain Base"): _auto(5.0, 40, 0.7),
    }
    verify = ResolvedPrice(
        None, 0.0, 0.0, "unresolved", "https://www.pathofexile.com/trade/search/L?q=x"
    )
    engine = ScanEngine(
        TransformRegistry([priced, prov], "v"),
        StubResolver(auto, verify),
        _settings(),
        clock=_clock,
    )
    rows = engine.scan("L")
    assert [r.transform_id for r in rows] == ["priced", "prov"]


def test_verify_with_resolved_price_ranks_after_confirmed_auto() -> None:
    """verify-mode row that resolves a real price must still rank after confirmed auto rows.

    The verify transform (verify_high) has input=10c, output=90c -> margin=80.
    The auto transform (auto_low) has input=10c, output=30c -> margin=20.
    Despite the verify row's higher raw margin, it must sort AFTER the confirmed auto row.
    """

    class PerRefStubResolver:
        """Resolver that uses per-ref price maps for both auto and verify lookups."""

        def __init__(
            self,
            prices: dict[tuple[str, str], ResolvedPrice],
        ) -> None:
            self._prices = prices

        def clear_cache(self) -> None:
            pass

        def resolve_auto(self, ref: PriceRef, league: str) -> ResolvedPrice:
            return self._prices[(ref.category, ref.key)]

        def resolve_verify(self, ref: PriceRef, league: str) -> ResolvedPrice:
            return self._prices[(ref.category, ref.key)]

    auto_t = _t("auto_low", "Currency", "Chaos Orb", "Fossil", "A")
    verify_t = _t("verify_high", "Currency", "Chaos Orb", "Fossil", "B", mode="verify")
    prices = {
        ("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
        ("Fossil", "A"): _auto(30.0, 50, 0.8),  # auto margin = 30 - 10 = 20
        ("Fossil", "B"): _auto(90.0, 50, 0.8),  # verify margin = 90 - 10 = 80 (higher raw)
    }
    engine = ScanEngine(
        TransformRegistry([auto_t, verify_t], "v"),
        PerRefStubResolver(prices),
        _settings(),
        clock=_clock,
    )
    rows = engine.scan("L")
    # verify row has margin 80 > auto row margin 20, but must still appear last
    assert len(rows) == 2
    assert rows[0].transform_id == "auto_low"
    assert rows[0].pricing_mode == "auto"
    assert rows[1].transform_id == "verify_high"
    assert rows[1].pricing_mode == "verify"


def _bracket(
    chaos: float, buy: float, sell: float, liq: float = 50, conf: float = 0.8
) -> ResolvedPrice:
    return ResolvedPrice(
        chaos_value=chaos,
        liquidity=liq,
        confidence=conf,
        source="ninja:x",
        deep_link=None,
        buy_value=buy,
        sell_value=sell,
    )


def test_bracketing_inputs_use_buy_outputs_use_sell() -> None:
    # ADR-0007: input costs the BUY (high) price; output realizes the SELL (low) price.
    t = _t("brk", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {
        ("Currency", "Chaos Orb"): _bracket(10.0, 12.0, 8.0),  # buy 12
        ("Fossil", "A"): _bracket(100.0, 110.0, 90.0),  # sell 90
    }
    engine = ScanEngine(
        TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)), _settings(), clock=_clock
    )
    row = engine.scan("L")[0]
    assert row.input_cost == 12.0  # buy side, not mid/sell
    assert row.output_value == 90.0  # sell side, not mid/buy
    assert row.margin == 78.0  # 90 - 12


def test_margin_confidence_thin_below_noise_floor() -> None:
    # margin passes the absolute gate but its % is within pricing noise -> flagged thin.
    t = _t("thinpct", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {
        ("Currency", "Chaos Orb"): _bracket(100.0, 100.0, 100.0),
        ("Fossil", "A"): _bracket(115.0, 115.0, 115.0),  # margin 15 (>=min_margin), 15% < 20%
    }
    engine = ScanEngine(
        TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)), _settings(), clock=_clock
    )
    row = engine.scan("L")[0]
    assert row.margin == 15.0 and row.margin_confidence == "thin"


def test_thin_margin_ranks_below_firm_even_with_bigger_absolute_margin() -> None:
    # firm: margin 50 at 50% (firm). thin: margin 100 at 10% (thin, bigger absolute).
    firm = _t("firm", "Currency", "Chaos Orb", "Fossil", "A")
    thin = _t("thin", "Currency", "Divine Orb", "Fossil", "B")
    auto = {
        ("Currency", "Chaos Orb"): _bracket(100.0, 100.0, 100.0),
        ("Fossil", "A"): _bracket(150.0, 150.0, 150.0),  # margin 50 -> 50% firm
        ("Currency", "Divine Orb"): _bracket(1000.0, 1000.0, 1000.0),
        ("Fossil", "B"): _bracket(1100.0, 1100.0, 1100.0),  # margin 100 -> 10% thin
    }
    engine = ScanEngine(
        TransformRegistry([firm, thin], "v"),
        StubResolver(auto, _auto(0, 0, 0)),
        _settings(),
        clock=_clock,
    )
    rows = engine.scan("L")
    ids = [r.transform_id for r in rows]
    assert ids == ["firm", "thin"]  # firm ranks first despite thin's larger absolute margin
    assert next(r for r in rows if r.transform_id == "thin").margin_confidence == "thin"


def test_min_margin_override() -> None:
    t = _t("thin", "Currency", "Chaos Orb", "Fossil", "A")
    auto = {
        ("Currency", "Chaos Orb"): _auto(10.0, 100, 0.9),
        ("Fossil", "A"): _auto(20.0, 50, 0.8),
    }  # margin 10
    engine = ScanEngine(
        TransformRegistry([t], "v"), StubResolver(auto, _auto(0, 0, 0)), _settings(), clock=_clock
    )
    assert engine.scan("L", min_margin=5.0)  # now passes with override
