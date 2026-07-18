from typing import Any

from pydantic import BaseModel

from oracle.http.client import HttpClient

CURRENCY_OVERVIEW_URL = "https://poe.ninja/api/data/currencyoverview"
ITEM_OVERVIEW_URL = "https://poe.ninja/api/data/itemoverview"


class NinjaSchemaError(Exception):
    """poe.ninja returned an unexpected shape."""


class NinjaLine(BaseModel):
    key: str
    chaos_value: float
    sample_depth: int


class NinjaClient:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def currency_overview(self, league: str) -> list[NinjaLine]:
        payload = self._http.get_json(
            CURRENCY_OVERVIEW_URL, params={"league": league, "type": "Currency"}
        )
        return self._parse_currency(payload)

    def item_overview(self, league: str, category: str) -> list[NinjaLine]:
        payload = self._http.get_json(
            ITEM_OVERVIEW_URL, params={"league": league, "type": category}
        )
        return self._parse_items(payload)

    def league_is_covered(self, league: str) -> bool:
        try:
            return bool(self.currency_overview(league))
        except Exception:
            return False

    @staticmethod
    def _parse_currency(payload: Any) -> list[NinjaLine]:
        if not isinstance(payload, dict) or "lines" not in payload:
            raise NinjaSchemaError("missing 'lines'")
        out: list[NinjaLine] = []
        for line in payload["lines"]:
            try:
                out.append(
                    NinjaLine(
                        key=line["currencyTypeName"],
                        chaos_value=float(line["chaosEquivalent"]),
                        sample_depth=int(line.get("receive", {}).get("count", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise NinjaSchemaError(str(exc)) from exc
        return out

    @staticmethod
    def _parse_items(payload: Any) -> list[NinjaLine]:
        if not isinstance(payload, dict) or "lines" not in payload:
            raise NinjaSchemaError("missing 'lines'")
        out: list[NinjaLine] = []
        for line in payload["lines"]:
            try:
                out.append(
                    NinjaLine(
                        key=line["name"],
                        chaos_value=float(line["chaosValue"]),
                        sample_depth=int(line.get("listingCount", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise NinjaSchemaError(str(exc)) from exc
        return out
