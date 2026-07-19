import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_PATH = Path("config/settings.toml")


class PricingSettings(BaseModel):
    percentile: float = Field(gt=0.0, lt=1.0)  # sell/output percentile (low = conservative)
    outlier_z: float = Field(gt=0.0)
    min_sample_depth: int = Field(ge=1)
    # Buy/input percentile (high = conservative: assume you pay the upper end). Bracketing
    # the two sides removes aggregation-manufactured phantom margins (ADR-0007).
    buy_percentile: float = Field(default=0.85, gt=0.0, lt=1.0)


class CacheSettings(BaseModel):
    ninja_ttl_seconds: int = Field(ge=1)
    league_ttl_seconds: int = Field(ge=1)
    observed_price_ttl_seconds: int = Field(ge=1)


class StoreSettings(BaseModel):
    db_path: str


class ScannerSettings(BaseModel):
    min_margin: float = Field(ge=0.0)
    min_liquidity: float = Field(ge=0.0)
    # Auto rows with margin_pct below this are within pricing noise -> flagged "thin"
    # margin and ranked below firm rows (ADR-0007). Default 20%.
    min_margin_pct: float = Field(default=0.20, ge=0.0)


class T2Settings(BaseModel):
    prob_sum_tolerance: float = Field(gt=0.0)
    default_service_cost: float = Field(ge=0.0)
    mc_trials: int = Field(ge=1)
    mc_seed: int = Field(ge=0)


class Settings(BaseModel):
    default_league: str
    realm: str
    user_agent: str
    pricing: PricingSettings
    cache: CacheSettings
    store: StoreSettings
    scanner: ScannerSettings
    t2: T2Settings


def load_settings(path: Path | None = None) -> Settings:
    p = path or DEFAULT_PATH
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    return Settings.model_validate(raw)
