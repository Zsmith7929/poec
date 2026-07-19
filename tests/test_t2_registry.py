from pathlib import Path

import pytest

from oracle.scanner.t2_registry import (
    DEFAULT_ODDS_DIR,
    OddsRegistry,
    OddsRegistryError,
    load_odds_registry,
)

TOL = 0.01


def test_loads_default_seed_and_versions() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    assert isinstance(reg, OddsRegistry)
    assert reg.version.startswith("sha256:")
    assert len(reg.tables) >= 3  # seed: vaal amulet, temple double-corrupt, tainted


def test_seed_ids_unique() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    ids = [t.id for t in reg.tables]
    assert len(ids) == len(set(ids))


def test_seed_tables_cite_source_and_probs_sum() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    for t in reg.tables:
        assert t.source, f"{t.id} missing source"
        total = sum(o.probability for o in t.outcomes)
        assert abs(total - 1.0) <= TOL, f"{t.id} sums to {total}"


def test_seed_has_bricked_salvage_outcome() -> None:
    reg = load_odds_registry(DEFAULT_ODDS_DIR, TOL)
    all_notes = " ".join(o.notes.lower() for t in reg.tables for o in t.outcomes)
    assert "brick" in all_notes  # at least one bricked/salvage outcome documented


def test_enabled_filters_disabled(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "tables.yaml").write_text(
        "tables:\n"
        "  - id: enabled-table\n    name: Enabled\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: https://example.com/odds\n    enabled: true\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: X}, probability: 1.0}\n"
        "  - id: disabled-table\n    name: Disabled\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: https://example.com/odds\n    enabled: false\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: Y}, probability: 1.0}\n"
    )
    reg = load_odds_registry(d, TOL)
    enabled = reg.enabled()
    assert len(enabled) == 1
    assert enabled[0].id == "enabled-table"


def test_version_changes_with_content(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "a.yaml").write_text(
        "tables:\n  - id: t1\n    name: A\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: s\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: X}, probability: 1.0}\n"
    )
    v1 = load_odds_registry(d, TOL).version
    (d / "a.yaml").write_text(
        "tables:\n  - id: t1\n    name: B\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: s\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: X}, probability: 1.0}\n"
    )
    v2 = load_odds_registry(d, TOL).version
    assert v1 != v2


def test_bad_probability_sum_fails_loud(tmp_path: Path) -> None:
    # Table is fully well-formed (has source, valid input, valid outcomes) — the ONLY
    # reason the registry should reject it is that 0.3 + 0.3 = 0.6 ≠ 1.0.
    d = tmp_path / "odds"
    d.mkdir()
    (d / "bad.yaml").write_text(
        "tables:\n  - id: t1\n    name: A\n"
        "    input: {category: Currency, key: Vaal Orb}\n"
        "    source: https://example.com/odds\n    outcomes:\n"
        "      - {result: {category: UniqueAccessory, key: X}, probability: 0.3}\n"
        "      - {result: {category: UniqueAccessory, key: Y}, probability: 0.3}\n"
    )
    with pytest.raises(OddsRegistryError, match="sum|tolerance|probabilit"):
        load_odds_registry(d, TOL)


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "bad.yaml").write_text("tables:\n  - id: t1\n    name: A\n    unexpected_key: 1\n")
    with pytest.raises(OddsRegistryError):
        load_odds_registry(d, TOL)


def test_missing_tables_key_fails_loud(tmp_path: Path) -> None:
    d = tmp_path / "odds"
    d.mkdir()
    (d / "bad.yaml").write_text("not_tables: []\n")
    with pytest.raises(OddsRegistryError):
        load_odds_registry(d, TOL)
