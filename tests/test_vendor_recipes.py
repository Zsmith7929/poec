from pathlib import Path

import pytest

from oracle.metadata.models import MetadataSource, VendorRecipe, VendorRecipeDoc, VendorRecipeItem
from oracle.metadata.vendor_recipes import (
    VendorRecipeError,
    expand_vendor_recipes,
    load_vendor_recipes,
    parse_vendor_recipes_html,
)

FIX = Path(__file__).parent / "fixtures" / "poedb_vendor_recipes.html"


# --- parser (pinned fixture: a poedb restyle must fail loud here) -----------


def test_parser_extracts_currency_recipes() -> None:
    recipes = parse_vendor_recipes_html(FIX.read_text())
    by_id = {r.id: r for r in recipes}
    # Fusing <- 4x Jeweller's is the canonical directional check.
    fusing = by_id["orb_of_fusing_from_jeweller_s_orb"]
    assert fusing.output == VendorRecipeItem(name="Orb of Fusing", qty=1.0)
    assert fusing.inputs == [VendorRecipeItem(name="Jeweller's Orb", qty=4.0)]
    assert fusing.npc == "Act 2 Yeena"
    # Oil blending 3 -> 1 is a real mechanic and must be captured.
    assert "amber_oil_from_sepia_oil" in by_id


def test_parser_skips_conditional_and_noncurrency_rows() -> None:
    recipes = parse_vendor_recipes_html(FIX.read_text())
    ids = {r.id for r in recipes}
    # "7x Jeweller's <- 6 Sockets" has a non-currency condition -> skipped.
    assert not any(r_id.endswith("_from_") or "socket" in r_id for r_id in ids)
    # gem output (non-currency) -> skipped.
    assert not any("gem" in r_id for r_id in ids)
    assert len(recipes) == 3  # fusing, chromatic, amber oil


def test_parser_empty_on_unrelated_html() -> None:
    assert parse_vendor_recipes_html("<html><body>no tables</body></html>") == []


# --- loader (fail-loud, versioned) -----------------------------------------


def _doc_yaml() -> str:
    return (
        "source:\n"
        "  url: https://poedb.tw/us/Vendor_recipe_system\n"
        "  fetched_at: '2026-07-19'\n"
        "  page_sha256: abc123\n"
        "recipes:\n"
        "  - id: orb_of_fusing_from_jeweller_s_orb\n"
        "    output: {name: Orb of Fusing, qty: 1.0}\n"
        "    inputs:\n"
        "      - {name: Jeweller's Orb, qty: 4.0}\n"
        "    npc: Act 2 Yeena\n"
    )


def test_loads_and_versions(tmp_path: Path) -> None:
    p = tmp_path / "vr.yaml"
    p.write_text(_doc_yaml())
    doc, version = load_vendor_recipes(p)
    assert isinstance(doc, VendorRecipeDoc)
    assert version.startswith("sha256:")
    assert len(doc.recipes) == 1


def test_version_changes_with_content(tmp_path: Path) -> None:
    a = tmp_path / "a.yaml"
    a.write_text(_doc_yaml())
    b = tmp_path / "b.yaml"
    b.write_text(_doc_yaml().replace("qty: 4.0", "qty: 5.0"))
    assert load_vendor_recipes(a)[1] != load_vendor_recipes(b)[1]


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "source: {url: u, fetched_at: d, page_sha256: s}\nrecipes:\n  - id: x\n    junk: 1\n"
    )
    with pytest.raises(VendorRecipeError):
        load_vendor_recipes(bad)


def test_missing_source_fails_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("recipes: []\n")
    with pytest.raises(VendorRecipeError):
        load_vendor_recipes(bad)


def test_duplicate_ids_fail_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    dup = _doc_yaml() + (
        "  - id: orb_of_fusing_from_jeweller_s_orb\n"
        "    output: {name: Orb of Fusing, qty: 1.0}\n"
        "    inputs:\n      - {name: Jeweller's Orb, qty: 4.0}\n"
    )
    bad.write_text(dup)
    with pytest.raises(VendorRecipeError):
        load_vendor_recipes(bad)


# --- expander ---------------------------------------------------------------


def test_expand_produces_grounded_transforms() -> None:
    doc = VendorRecipeDoc(
        source=MetadataSource(url="u", fetched_at="2026-07-19", page_sha256="s"),
        recipes=[
            VendorRecipe(
                id="orb_of_fusing_from_jeweller_s_orb",
                output=VendorRecipeItem(name="Orb of Fusing", qty=1.0),
                inputs=[VendorRecipeItem(name="Jeweller's Orb", qty=4.0)],
                npc="Act 2 Yeena",
            )
        ],
    )
    transforms = expand_vendor_recipes(doc)
    assert len(transforms) == 1
    t = transforms[0]
    assert t.id == "vendor::orb_of_fusing_from_jeweller_s_orb"
    assert t.pricing_mode == "auto"
    assert t.output.category == "Currency" and t.output.key == "Orb of Fusing"
    assert t.inputs[0].category == "Currency"
    assert t.inputs[0].key == "Jeweller's Orb" and t.inputs[0].qty == 4.0
    assert "4x Jeweller's Orb" in t.name


# --- end-to-end: an expanded recipe prices through the real ScanEngine -------


def test_expanded_recipe_prices_through_scan_engine() -> None:
    from datetime import UTC, datetime

    from oracle.config import ScannerSettings
    from oracle.models import ListingQuote, Price
    from oracle.scanner.engine import ScanEngine
    from oracle.scanner.registry import TransformRegistry
    from oracle.scanner.resolve import PriceResolver

    class CurrencyPrices:
        def prices(self, category: str, league: str) -> list[Price]:
            now = datetime.now(tz=UTC)
            table = {"Orb of Fusing": (15.0, 500), "Jeweller's Orb": (1.0, 900)}
            return [
                Price(
                    key=k,
                    league=league,
                    category=category,
                    chaos_value=v,
                    sample_depth=d,
                    source=f"ninja:{category}",
                    confidence=0.9,
                    ts=now,
                    demand="active",
                )
                for k, (v, d) in table.items()
                if category == "Currency"
            ]

    class NullDeepLink:
        def resolve(self, spec, league):  # type: ignore[no-untyped-def]
            return ListingQuote(
                spec_hash="h",
                league=league,
                chaos_value=None,
                deep_link="https://example.com",
                source="unresolved",
                observed_ts=None,
            )

    doc = VendorRecipeDoc(
        source=MetadataSource(url="u", fetched_at="2026-07-19", page_sha256="s"),
        recipes=[
            VendorRecipe(
                id="orb_of_fusing_from_jeweller_s_orb",
                output=VendorRecipeItem(name="Orb of Fusing", qty=1.0),
                inputs=[VendorRecipeItem(name="Jeweller's Orb", qty=4.0)],
                npc="Act 2 Yeena",
            )
        ],
    )
    reg = TransformRegistry(expand_vendor_recipes(doc), version="test")
    resolver = PriceResolver(CurrencyPrices(), NullDeepLink(), min_sample_depth=5)
    engine = ScanEngine(reg, resolver, ScannerSettings(min_margin=1.0, min_liquidity=1.0))
    rows = engine.scan("AnyLeague")
    row = next(r for r in rows if r.transform_id == "vendor::orb_of_fusing_from_jeweller_s_orb")
    # margin = price(Fusing) - 4*price(Jeweller's) - friction = 15 - 4 - 0 = 11
    assert row.margin == 11.0
    assert row.input_cost == 4.0
    # Output-leg demand ("active" from high-volume Fusing) propagates to the row.
    assert row.demand == "active"
