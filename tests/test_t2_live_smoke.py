import pytest

from oracle.app import build_services

pytestmark = pytest.mark.live


def test_t2_evaluates_against_default_league_live() -> None:
    svc = build_services()
    default = svc.settings.default_league
    rows = svc.t2.evaluate(default)
    assert rows  # enabled seed tables evaluated
    for r in rows:
        # EV numbers are finite; unresolved outcomes surfaced, never fabricated.
        assert r.ev_gross == r.ev_gross  # not NaN
        assert r.unresolved_outcomes >= 0


def test_scan_includes_probabilistic_section_live() -> None:
    svc = build_services()
    report, _md, _json = svc.scan.run(svc.settings.default_league)
    assert "PROBABILISTIC (Tier-2)" in report.to_terminal()
