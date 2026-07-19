import hashlib
import json
from datetime import datetime

from pydantic import BaseModel


class League(BaseModel):
    id: str
    realm: str
    ninja_available: bool


class Price(BaseModel):
    key: str
    league: str
    category: str
    chaos_value: float
    sample_depth: int
    source: str
    confidence: float
    ts: datetime


class Maturity(BaseModel):
    league: str
    median_sample_depth: float
    volatility: float
    history_density: float
    score: float


class Mod(BaseModel):
    id: str
    name: str
    weight: int
    group: str
    tags: list[str]
    domain: str
    generation_type: str
    required_level: int = 0


class ModFilter(BaseModel):
    stat_id: str
    min_value: float | None = None


class ItemSpec(BaseModel):
    base: str
    ilvl: int | None = None
    influence: str | None = None
    mod_filters: list[ModFilter] = []
    sockets: int | None = None
    links: int | None = None

    def spec_hash(self) -> str:
        payload = {
            "base": self.base,
            "ilvl": self.ilvl,
            "influence": self.influence,
            "mod_filters": sorted(
                ([f.stat_id, f.min_value] for f in self.mod_filters),
                key=lambda x: str(x[0]),
            ),
            "sockets": self.sockets,
            "links": self.links,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


class ListingQuote(BaseModel):
    spec_hash: str
    league: str
    chaos_value: float | None
    deep_link: str
    residual_instructions: list[str] = []
    source: str
    observed_ts: datetime | None = None
