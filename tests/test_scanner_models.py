from datetime import UTC, datetime

from oracle.config import ScannerSettings, load_settings
from oracle.scanner.models import PriceRef, ScanRow, Transform


def test_priceref_defaults() -> None:
    ref = PriceRef(category="Currency", key="Divine Orb")
    assert ref.qty == 1.0
    assert ref.influence is None
    assert ref.ilvl is None


def test_transform_defaults_to_auto_enabled() -> None:
    t = Transform(
        id="t1",
        name="Example",
        inputs=[PriceRef(category="Currency", key="Chaos Orb")],
        output=PriceRef(category="Fossil", key="Some Fossil"),
    )
    assert t.enabled is True
    assert t.pricing_mode == "auto"
    assert t.friction == 0.0


def test_transform_rejects_unknown_pricing_mode() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Transform(
            id="t1",
            name="Example",
            inputs=[PriceRef(category="Currency", key="Chaos Orb")],
            output=PriceRef(category="Fossil", key="Some Fossil"),
            pricing_mode="wat",  # type: ignore[arg-type]
        )


def test_transform_rejects_unknown_field() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Transform(
            id="x",
            name="X",
            inputs=[],
            output=PriceRef(category="Currency", key="Chaos Orb"),
            catgory="typo",  # type: ignore[call-arg]
        )


def test_scanrow_allows_none_output_for_verify() -> None:
    row = ScanRow(
        transform_id="t1",
        name="Example",
        input_cost=10.0,
        output_value=None,
        margin=None,
        margin_pct=None,
        liquidity=0.0,
        confidence=0.0,
        pricing_mode="verify",
        deep_link="https://www.pathofexile.com/trade/search/X?q=...",
        source="verify",
        ts=datetime.now(tz=UTC),
    )
    assert row.output_value is None
    assert row.deep_link is not None


def test_scanner_settings_loaded_from_config() -> None:
    settings = load_settings()
    assert isinstance(settings.scanner, ScannerSettings)
    assert settings.scanner.min_margin >= 0.0
    assert settings.scanner.min_liquidity >= 0.0
