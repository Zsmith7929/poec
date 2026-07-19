from dataclasses import dataclass
from pathlib import Path

from oracle.config import Settings, load_settings
from oracle.gamedata.service import GameDataService
from oracle.http.client import HttpClient
from oracle.league.service import LeagueService
from oracle.metadata.vendor_recipes import (
    DEFAULT_VENDOR_RECIPES_PATH,
    expand_vendor_recipes,
    load_vendor_recipes,
)
from oracle.pricing.listings import DeepLinkResolver
from oracle.pricing.ninja import NinjaClient
from oracle.pricing.service import PriceService
from oracle.scanner.engine import ScanEngine
from oracle.scanner.registry import DEFAULT_TRANSFORMS_PATH, TransformRegistry, load_registry
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
    # Hand-authored one-offs, plus bulk grounded transforms expanded from cited
    # poedb metadata (ADR-0001/0003). Combined into one registry for the engine.
    base_registry = load_registry(DEFAULT_TRANSFORMS_PATH)
    vendor_doc, vendor_version = load_vendor_recipes(DEFAULT_VENDOR_RECIPES_PATH)
    all_transforms = base_registry.transforms + expand_vendor_recipes(vendor_doc)
    ids = [t.id for t in all_transforms]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"transform id collision across sources: {dupes}")
    combined = TransformRegistry(
        all_transforms, version=f"{base_registry.version}+{vendor_version}"
    )
    scan_resolver = PriceResolver(price, resolver, settings.pricing.min_sample_depth)
    engine = ScanEngine(combined, scan_resolver, settings.scanner)
    scan = ScanService(engine, ScanResultRepo(conn), combined.version, Path("reports"))
    return Services(
        settings=settings,
        league=LeagueService(http, ninja_probe=ninja.league_is_covered),
        gamedata=gamedata,
        price=price,
        resolver=resolver,
        scan=scan,
    )
