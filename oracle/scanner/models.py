from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PriceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    key: str
    qty: float = 1.0
    influence: str | None = None
    ilvl: int | None = None


class Transform(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    inputs: list[PriceRef]
    output: PriceRef
    applicability: str = ""
    friction: float = 0.0
    enabled: bool = True
    patch_validity: str = ""
    pricing_mode: Literal["auto", "verify"] = "auto"


class ScanRow(BaseModel):
    transform_id: str
    name: str
    input_cost: float
    output_value: float | None
    margin: float | None
    margin_pct: float | None
    liquidity: float
    confidence: float
    pricing_mode: str
    deep_link: str | None
    source: str
    ts: datetime
