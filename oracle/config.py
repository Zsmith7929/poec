import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_PATH = Path("config/settings.toml")


class PricingSettings(BaseModel):
    percentile: float = Field(gt=0.0, lt=1.0)
    outlier_z: float = Field(gt=0.0)
    min_sample_depth: int = Field(ge=1)


class CacheSettings(BaseModel):
    ninja_ttl_seconds: int = Field(ge=1)
    league_ttl_seconds: int = Field(ge=1)
    observed_price_ttl_seconds: int = Field(ge=1)


class StoreSettings(BaseModel):
    db_path: str


class ScannerSettings(BaseModel):
    min_margin: float = Field(ge=0.0)
    min_liquidity: float = Field(ge=0.0)


class Settings(BaseModel):
    default_league: str
    realm: str
    user_agent: str
    pricing: PricingSettings
    cache: CacheSettings
    store: StoreSettings
    scanner: ScannerSettings


def load_settings(path: Path | None = None) -> Settings:
    p = path or DEFAULT_PATH
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    return Settings.model_validate(raw)
