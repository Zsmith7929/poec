from typing import Any

from pydantic import BaseModel

from oracle.http.client import HttpClient

LEAGUES_URL = "https://poe.ninja/poe1/api/economy/leagues"
OVERVIEW_URL = "https://poe.ninja/poe1/api/economy/exchange/current/overview"
STASH_OVERVIEW_URL = "https://poe.ninja/poe1/api/economy/stash/current/item/overview"


class NinjaSchemaError(Exception):
    """poe.ninja returned an unexpected shape."""


class NinjaLine(BaseModel):
    key: str
    chaos_value: float
    sample_depth: int


class StashLine(BaseModel):
    """A line from the stash item overview (uniques, base types, gems).

    Unlike the exchange feed, variants matter: base types repeat per (name, variant,
    ilvl). `variant` carries the influence discriminator ("Shaper", "Crusader/Redeemer",
    or None for a plain base); `ilvl` is levelRequired.
    """

    key: str
    chaos_value: float
    sample_depth: int  # listing count = SUPPLY, not demand (see ADR-0005)
    variant: str | None = None
    ilvl: int | None = None
    observations: int = 0  # poe.ninja `count`: data points behind the price
    trend: float = 0.0  # sparkline total % change over the window (price momentum)


class NinjaClient:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def overview(self, league: str, type_: str) -> list[NinjaLine]:
        payload = self._http.get_json(OVERVIEW_URL, params={"league": league, "type": type_})
        return self._parse_overview(payload)

    # Backward-compatible wrappers so PriceService keeps working unchanged.
    def currency_overview(self, league: str) -> list[NinjaLine]:
        return self.overview(league, "Currency")

    def item_overview(self, league: str, category: str) -> list[NinjaLine]:
        return self.overview(league, category)

    def stash_overview(self, league: str, type_: str) -> list[StashLine]:
        """Fetch the stash item overview (uniques, base types, gems) for a category."""
        payload = self._http.get_json(STASH_OVERVIEW_URL, params={"league": league, "type": type_})
        return self._parse_stash_overview(payload)

    @staticmethod
    def _parse_stash_overview(payload: Any) -> list[StashLine]:
        if not isinstance(payload, dict):
            raise NinjaSchemaError("payload is not a dict")
        if "lines" not in payload:
            raise NinjaSchemaError("missing 'lines'")
        raw_lines = payload["lines"]
        if not isinstance(raw_lines, list):
            raise NinjaSchemaError("'lines' is not a list")

        out: list[StashLine] = []
        for line in raw_lines:
            if not isinstance(line, dict):
                raise NinjaSchemaError("line entry is not a dict")
            if "name" not in line:
                raise NinjaSchemaError("line missing 'name'")
            # Skip unpriced lines rather than crash (mirrors the exchange sparse policy).
            if line.get("chaosValue") is None:
                continue
            try:
                lvl = line.get("levelRequired")
                spark = line.get("sparkLine") or {}
                out.append(
                    StashLine(
                        key=str(line["name"]),
                        chaos_value=float(line["chaosValue"]),
                        sample_depth=int(line.get("listingCount") or 0),
                        variant=line.get("variant"),
                        ilvl=None if lvl is None else int(lvl),
                        observations=int(line.get("count") or 0),
                        trend=float(spark.get("totalChange") or 0.0),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise NinjaSchemaError(str(exc)) from exc
        return out

    def league_is_covered(self, league: str) -> bool:
        try:
            payload = self._http.get_json(LEAGUES_URL)
            if not isinstance(payload, list):
                return False
            return any(isinstance(entry, dict) and entry.get("id") == league for entry in payload)
        except Exception:
            return False

    @staticmethod
    def _parse_overview(payload: Any) -> list[NinjaLine]:
        if not isinstance(payload, dict):
            raise NinjaSchemaError("payload is not a dict")
        if "lines" not in payload:
            raise NinjaSchemaError("missing 'lines'")
        if "items" not in payload:
            raise NinjaSchemaError("missing 'items'")

        raw_items = payload["items"]
        if not isinstance(raw_items, list):
            raise NinjaSchemaError("'items' is not a list")

        # Build id -> name mapping; drift if any item is missing id or name.
        id_to_name: dict[str, str] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                raise NinjaSchemaError("item entry is not a dict")
            if "id" not in item:
                raise NinjaSchemaError("item missing 'id'")
            if "name" not in item:
                raise NinjaSchemaError("item missing 'name'")
            id_to_name[item["id"]] = item["name"]

        raw_lines = payload["lines"]
        if not isinstance(raw_lines, list):
            raise NinjaSchemaError("'lines' is not a list")

        out: list[NinjaLine] = []
        for line in raw_lines:
            if not isinstance(line, dict):
                raise NinjaSchemaError("line entry is not a dict")
            if "id" not in line:
                raise NinjaSchemaError("line missing 'id'")
            # Some leagues return sparse entries (e.g. the chaos base with no primaryValue)
            # when liquidity is essentially zero.  Skip rather than crash.
            if "primaryValue" not in line or "volumePrimaryValue" not in line:
                continue
            line_id = line["id"]
            if line_id not in id_to_name:
                # Structural drift: a line has no matching item name.
                raise NinjaSchemaError(f"line id {line_id!r} has no matching entry in 'items'")
            try:
                out.append(
                    NinjaLine(
                        key=id_to_name[line_id],
                        chaos_value=float(line["primaryValue"]),
                        sample_depth=int(line["volumePrimaryValue"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise NinjaSchemaError(str(exc)) from exc
        return out
