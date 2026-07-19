from typing import Any

from pydantic import BaseModel

from oracle.http.client import HttpClient

LEAGUES_URL = "https://poe.ninja/poe1/api/economy/leagues"
OVERVIEW_URL = "https://poe.ninja/poe1/api/economy/exchange/current/overview"


class NinjaSchemaError(Exception):
    """poe.ninja returned an unexpected shape."""


class NinjaLine(BaseModel):
    key: str
    chaos_value: float
    sample_depth: int


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
            if "primaryValue" not in line:
                raise NinjaSchemaError("line missing 'primaryValue'")
            line_id = line["id"]
            if line_id not in id_to_name:
                # Structural drift: a line has no matching item name.
                raise NinjaSchemaError(f"line id {line_id!r} has no matching entry in 'items'")
            try:
                out.append(
                    NinjaLine(
                        key=id_to_name[line_id],
                        chaos_value=float(line["primaryValue"]),
                        sample_depth=int(line.get("volumePrimaryValue", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise NinjaSchemaError(str(exc)) from exc
        return out
