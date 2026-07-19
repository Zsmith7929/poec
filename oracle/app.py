from dataclasses import dataclass
from pathlib import Path

from oracle.config import Settings, load_settings
from oracle.gamedata.service import GameDataService
from oracle.http.client import HttpClient
from oracle.league.service import LeagueService
from oracle.pricing.listings import DeepLinkResolver
from oracle.pricing.ninja import NinjaClient
from oracle.pricing.service import PriceService
from oracle.scanner.engine import ScanEngine
from oracle.scanner.ev import EvEngine
from oracle.scanner.factory import FactoryEngine
from oracle.scanner.registry import DEFAULT_TRANSFORMS_PATH, load_registry
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.service import ScanService
from oracle.scanner.t2_registry import DEFAULT_ODDS_DIR, load_odds_registry
from oracle.scanner.t2_service import T2Service
from oracle.store.db import connect
from oracle.store.ev_results import EvResultRepo
from oracle.store.observations import ObservedPriceRepo
from oracle.store.scans import ScanResultRepo

HTTP_ALLOWED_HOSTS = {"api.pathofexile.com", "poe.ninja"}


@dataclass
class Services:
    settings: Settings
    league: LeagueService
    gamedata: GameDataService
    price: PriceService
    resolver: DeepLinkResolver
    scan: ScanService
    t2: T2Service


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or load_settings()
    http = HttpClient(settings.user_agent, HTTP_ALLOWED_HOSTS)
    ninja = NinjaClient(http)
    conn = connect(settings.store.db_path)
    gamedata = GameDataService.from_snapshot(Path("snapshots/repoe"))
    price = PriceService(ninja, conn, settings)
    resolver = DeepLinkResolver(ObservedPriceRepo(conn), settings.cache.observed_price_ttl_seconds)
    registry = load_registry(DEFAULT_TRANSFORMS_PATH)
    scan_resolver = PriceResolver(price, resolver, settings.pricing.min_sample_depth)
    engine = ScanEngine(registry, scan_resolver, settings.scanner)
    odds = load_odds_registry(DEFAULT_ODDS_DIR, settings.t2.prob_sum_tolerance)
    ev_engine = EvEngine(scan_resolver)
    factory_engine = FactoryEngine(ev_engine, scan_resolver)
    t2 = T2Service(ev_engine, factory_engine, odds, EvResultRepo(conn), odds.version)
    scan = ScanService(engine, ScanResultRepo(conn), registry.version, Path("reports"), t2=t2)
    return Services(
        settings=settings,
        league=LeagueService(http, ninja_probe=ninja.league_is_covered),
        gamedata=gamedata,
        price=price,
        resolver=resolver,
        scan=scan,
        t2=t2,
    )
