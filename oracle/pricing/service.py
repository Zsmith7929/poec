import sqlite3
from datetime import UTC, datetime
from typing import Protocol

from oracle.config import Settings
from oracle.models import Maturity, Price, price_storage_key
from oracle.pricing.aggregate import aggregate, confidence
from oracle.pricing.maturity import maturity_signals
from oracle.pricing.ninja import NinjaLine, StashLine
from oracle.store.prices import PriceSnapshotRepo

# Categories served by the stash item overview (variant-bearing) rather than the
# currency exchange overview. Anything else routes to the exchange feed.
STASH_TYPES = frozenset(
    {
        "UniqueWeapon",
        "UniqueArmour",
        "UniqueAccessory",
        "UniqueJewel",
        "UniqueFlask",
        "UniqueMap",
        "BaseType",
        "SkillGem",
        "ImbuedGem",
    }
)


class _Ninja(Protocol):
    def currency_overview(self, league: str) -> list[NinjaLine]: ...
    def item_overview(self, league: str, category: str) -> list[NinjaLine]: ...
    def stash_overview(self, league: str, type_: str) -> list[StashLine]: ...


class PriceService:
    def __init__(self, ninja: _Ninja, conn: sqlite3.Connection, settings: Settings) -> None:
        self._ninja = ninja
        self._repo = PriceSnapshotRepo(conn)
        self._settings = settings

    def prices(self, category: str, league: str) -> list[Price]:
        if category in STASH_TYPES:
            return self._stash_prices(category, league)
        if category.lower() == "currency":
            lines: list[NinjaLine] = self._ninja.currency_overview(league)
        else:
            lines = self._ninja.item_overview(league, category)
        mat = self.maturity(league)
        now = datetime.now(tz=UTC)
        out: list[Price] = []
        for line in lines:
            history = self._repo.recent_values(league, category, line.key)
            history.append(line.chaos_value)
            agg = aggregate(
                history, self._settings.pricing.percentile, self._settings.pricing.outlier_z
            )
            price = Price(
                key=line.key,
                league=league,
                category=category,
                chaos_value=agg.value,
                sample_depth=line.sample_depth,
                source=f"ninja:{category}",
                confidence=confidence(
                    line.sample_depth, self._settings.pricing.min_sample_depth, mat.score
                ),
                ts=now,
            )
            self._repo.insert(price)
            out.append(price)
        return out

    def _stash_prices(self, category: str, league: str) -> list[Price]:
        lines = self._ninja.stash_overview(league, category)
        mat = self.maturity(league)
        now = datetime.now(tz=UTC)
        out: list[Price] = []
        for line in lines:
            # Same key the write path uses (Price.storage_key), so history round-trips.
            hist_key = price_storage_key(line.key, line.variant, line.ilvl)
            history = self._repo.recent_values(league, category, hist_key)
            history.append(line.chaos_value)
            agg = aggregate(
                history, self._settings.pricing.percentile, self._settings.pricing.outlier_z
            )
            price = Price(
                key=line.key,
                league=league,
                category=category,
                chaos_value=agg.value,
                sample_depth=line.sample_depth,
                source=f"ninja:{category}",
                confidence=confidence(
                    line.sample_depth, self._settings.pricing.min_sample_depth, mat.score
                ),
                ts=now,
                variant=line.variant,
                ilvl=line.ilvl,
            )
            self._repo.insert(price)
            out.append(price)
        return out

    def maturity(self, league: str) -> Maturity:
        depths = self._repo.recent_depths(league)
        median_depth, vol, density, score = maturity_signals(depths, [], len(depths))
        return Maturity(
            league=league,
            median_sample_depth=median_depth,
            volatility=vol,
            history_density=density,
            score=score,
        )
