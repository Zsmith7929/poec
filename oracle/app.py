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
from oracle.scanner.registry import DEFAULT_TRANSFORMS_PATH, load_registry
from oracle.scanner.resolve import PriceResolver
from oracle.scanner.service import ScanService
from oracle.store.db import connect
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
    scan = ScanService(engine, ScanResultRepo(conn), registry.version, Path("reports"))
    return Services(
        settings=settings,
        league=LeagueService(http, ninja_probe=ninja.league_is_covered),
        gamedata=gamedata,
        price=price,
        resolver=resolver,
        scan=scan,
    )
