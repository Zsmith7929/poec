from pathlib import Path

import pytest

from oracle.scanner.registry import (
    DEFAULT_TRANSFORMS_PATH,
    TransformRegistry,
    TransformRegistryError,
    load_registry,
)


def test_loads_default_seed_and_versions() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    assert isinstance(reg, TransformRegistry)
    assert reg.version.startswith("sha256:")
    assert len(reg.transforms) >= 15  # seed target ~15-20


def test_enabled_filters_disabled() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    assert all(t.enabled for t in reg.enabled())
    # at least one disabled entry exists in the seed (patch-mechanic-dependent)
    assert any(not t.enabled for t in reg.transforms)


def test_disabled_entries_carry_patch_validity_note() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    for t in reg.transforms:
        if not t.enabled:
            assert t.patch_validity, f"{t.id} disabled without a patch_validity note"


def test_ids_are_unique() -> None:
    reg = load_registry(DEFAULT_TRANSFORMS_PATH)
    ids = [t.id for t in reg.transforms]
    assert len(ids) == len(set(ids))


def test_version_changes_with_content(tmp_path: Path) -> None:
    a = tmp_path / "a.yaml"
    a.write_text(
        "transforms:\n"
        "  - id: t1\n    name: A\n    inputs:\n"
        "      - {category: Currency, key: Chaos Orb}\n"
        "    output: {category: Fossil, key: F}\n"
    )
    b = tmp_path / "b.yaml"
    b.write_text(
        "transforms:\n"
        "  - id: t1\n    name: B\n    inputs:\n"
        "      - {category: Currency, key: Chaos Orb}\n"
        "    output: {category: Fossil, key: F}\n"
    )
    assert load_registry(a).version != load_registry(b).version


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("transforms:\n  - id: t1\n    unexpected_key: 1\n")
    with pytest.raises(TransformRegistryError):
        load_registry(bad)


def test_missing_transforms_key_fails_loud(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("not_transforms: []\n")
    with pytest.raises(TransformRegistryError):
        load_registry(bad)
