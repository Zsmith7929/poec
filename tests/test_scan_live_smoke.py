import pytest

from oracle.app import build_services

pytestmark = pytest.mark.live


def test_scan_runs_against_default_league_live() -> None:
    svc = build_services()
    default = svc.settings.default_league
    report, md_path, json_path = svc.scan.run(default)
    assert report.league == default
    assert report.rule_version.startswith("sha256:")
    assert md_path.exists() and json_path.exists()
    # auto rows, when present, must be ranked by margin descending
    margins = [r.margin for r in report.auto_rows() if r.margin is not None]
    assert margins == sorted(margins, reverse=True)


def test_scan_runs_against_second_live_league_no_code_change() -> None:
    svc = build_services()
    live = [lg for lg in svc.league.list_leagues() if lg.ninja_available]
    if len(live) < 2:
        pytest.skip("need >=2 ninja-covered leagues to prove league-agnosticism live")
    for lg in live[:2]:
        report, _, _ = svc.scan.run(lg.id)
        assert report.league == lg.id
