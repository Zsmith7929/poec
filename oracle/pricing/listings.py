"""ListingResolver — builds trade-site deep links; performs ZERO network I/O.

See docs/trade-deeplinks.md for the URL format specification.
"""

import json
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote

from oracle.models import ItemSpec, ListingQuote

TRADE_SITE_BASE = "https://www.pathofexile.com/trade/search"


class _ObsRepo(Protocol):
    def record(self, league: str, spec_hash: str, chaos_value: float, ts: str) -> None: ...

    def latest(self, league: str, spec_hash: str, ttl_seconds: int) -> tuple[float, str] | None: ...


class ListingResolver(Protocol):
    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote: ...


def _build_query(spec: ItemSpec) -> tuple[str, list[str]]:
    """Return (url-encoded query JSON fragment, residual human instructions).

    Builds the query object documented in docs/trade-deeplinks.md.
    Filters that cannot be encoded in the URL (e.g. influence in v1) are
    returned as human-readable residual instructions rather than silently
    dropped.

    No network I/O is performed — this is pure string construction.
    """
    residual: list[str] = []

    stats: list[dict[str, object]] = []
    for f in spec.mod_filters:
        if f.min_value is not None:
            stats.append({"id": f.stat_id, "value": {"min": f.min_value}})
        else:
            residual.append(f"Add mod filter: {f.stat_id} (no min value set)")

    misc_filters: dict[str, object] = {}
    if spec.ilvl is not None:
        misc_filters = {"filters": {"ilvl": {"min": spec.ilvl}}}

    filters: dict[str, object] = {"type_filters": {"filters": {}}}
    if misc_filters:
        filters["misc_filters"] = misc_filters

    query_inner: dict[str, object] = {
        "status": {"option": "online"},
        "type": spec.base,
        "filters": filters,
    }
    if stats:
        query_inner["stats"] = [{"type": "and", "filters": stats}]

    if spec.influence is not None:
        residual.append(f"Set influence filter: {spec.influence}")

    query: dict[str, object] = {
        "query": query_inner,
        "sort": {"price": "asc"},
    }

    encoded = quote(json.dumps(query, separators=(",", ":")))
    return encoded, residual


class DeepLinkResolver:
    """Resolves an ItemSpec to a trade-site deep link + optional cached price.

    ``resolve`` never makes an HTTP request; it only constructs a URL string
    and optionally returns a previously recorded user-observed price.
    """

    def __init__(self, observed_repo: _ObsRepo, ttl_seconds: int) -> None:
        self._repo = observed_repo
        self._ttl = ttl_seconds

    def _deep_link(self, spec: ItemSpec, league: str) -> tuple[str, list[str]]:
        encoded, residual = _build_query(spec)
        url = f"{TRADE_SITE_BASE}/{quote(league)}?q={encoded}"
        return url, residual

    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote:
        h = spec.spec_hash()
        url, residual = self._deep_link(spec, league)
        cached = self._repo.latest(league, h, self._ttl)
        if cached is not None:
            value, ts = cached
            return ListingQuote(
                spec_hash=h,
                league=league,
                chaos_value=value,
                deep_link=url,
                residual_instructions=residual,
                source="user-observed",
                observed_ts=datetime.fromisoformat(ts),
            )
        return ListingQuote(
            spec_hash=h,
            league=league,
            chaos_value=None,
            deep_link=url,
            residual_instructions=residual,
            source="unresolved",
            observed_ts=None,
        )

    def record_observed_price(self, spec: ItemSpec, league: str, chaos_value: float) -> None:
        ts = datetime.now(tz=UTC).isoformat()
        self._repo.record(league, spec.spec_hash(), chaos_value, ts)
