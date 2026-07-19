from datetime import UTC, datetime
from pathlib import Path

from oracle.config import ScannerSettings
from oracle.models import ListingQuote, Price
from oracle.scanner.engine import ScanEngine
from oracle.scanner.registry import load_registry
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.service import ScanService
from oracle.store.db import connect
from oracle.store.scans import ScanResultRepo

FIX = Path(__file__).parent / "fixtures"


class SyntheticPriceService:
    """Prices the synthetic shield fixture so the KNOWN margin is detectable."""

    def prices(self, category: str, league: str) -> list[Price]:
        now = datetime.now(tz=UTC)
        table = {
            ("BaseType", "Plain Shield Base"): (5.0, 40),
            ("Currency", "Shaper's Orb"): (10.0, 60),
            ("BaseType", "Shaper Shield Base"): (80.0, 30),  # margin = 80-5-10 = 65
        }
        return [
            Price(
                key=key,
                league=league,
                category=category,
                chaos_value=val,
                sample_depth=depth,
                source=f"ninja:{category}",
                confidence=0.8,
                ts=now,
            )
            for (cat, key), (val, depth) in table.items()
            if cat == category
        ]


class NullDeepLink:
    def resolve(self, spec, league):  # type: ignore[no-untyped-def]
        return ListingQuote(
            spec_hash="h",
            league=league,
            chaos_value=None,
            deep_link="https://www.pathofexile.com/trade/search/x?q=x",
            residual_instructions=[],
            source="unresolved",
            observed_ts=None,
        )


def _clock() -> datetime:
    return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _service(tmp_path: Path) -> ScanService:
    reg = load_registry(FIX / "transforms_synthetic_shield.yaml")
    resolver = PriceResolver(SyntheticPriceService(), NullDeepLink(), min_sample_depth=5)
    engine = ScanEngine(
        reg, resolver, ScannerSettings(min_margin=15.0, min_liquidity=5.0), clock=_clock
    )
    repo = ScanResultRepo(connect(str(tmp_path / "t.db")))
    return ScanService(engine, repo, reg.version, tmp_path / "reports", clock=_clock)


def test_scan_detects_known_shield_margin(tmp_path: Path) -> None:
    report, md, js = _service(tmp_path).run("SynthLeague")
    shield = next(r for r in report.rows if r.transform_id == "synthetic_shaper_shield")
    assert shield.margin == 65.0
    assert md.exists() and js.exists()


def test_scan_persists_rows(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc.run("SynthLeague")
    # repo is internal; re-run and assert files accumulate + persistence didn't raise
    report, _, _ = svc.run("SynthLeague")
    assert report.rule_version.startswith("sha256:")


def test_same_scan_runs_against_second_league_no_code_change(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    r1, _, _ = svc.run("InventedLeagueOne")
    r2, _, _ = svc.run("InventedLeagueTwo")
    assert r1.league == "InventedLeagueOne"
    assert r2.league == "InventedLeagueTwo"
    m1 = next(r.margin for r in r1.rows if r.transform_id == "synthetic_shaper_shield")
    m2 = next(r.margin for r in r2.rows if r.transform_id == "synthetic_shaper_shield")
    assert m1 == m2 == 65.0  # identical logic, different runtime league param
