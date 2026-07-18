from pathlib import Path

from oracle.gamedata.service import GameDataService
from oracle.models import Mod

SNAP = Path("snapshots/repoe")


def test_loads_snapshot_and_reports_version() -> None:
    svc = GameDataService.from_snapshot(SNAP)
    assert svc.snapshot_version()  # non-empty


def test_mod_pool_returns_weighted_mods_for_known_base() -> None:
    svc = GameDataService.from_snapshot(SNAP)
    pool = svc.mod_pool("Vaal Regalia", ilvl=86)
    assert pool, "expected a non-empty mod pool"
    assert all(isinstance(m, Mod) for m in pool)
    assert all(m.weight >= 0 for m in pool)
    # ilvl gate: no mod with a required level above the item level
    assert all(getattr(m, "required_level", 0) <= 86 for m in pool)


def test_unknown_shape_fails_loud(tmp_path: Path) -> None:
    import pytest

    bad = tmp_path / "repoe"
    bad.mkdir()
    (bad / "manifest.json").write_text('{"files": ["mods.min.json"]}')
    (bad / "mods.min.json").write_text('{"BadMod": {"unexpected": 1}}')
    with pytest.raises(Exception):  # noqa: B017
        GameDataService.from_snapshot(bad)
