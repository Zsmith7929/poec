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
