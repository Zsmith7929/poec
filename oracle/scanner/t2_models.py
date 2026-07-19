from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from oracle.scanner.models import PriceRef


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: PriceRef
    probability: float = Field(ge=0.0, le=1.0)
    notes: str = ""


class OddsTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    input: PriceRef
    service_cost: float = 0.0
    outcomes: list[Outcome]
    source: str
    patch_validity: str = ""
    enabled: bool = True
    prob_sum_tolerance: float | None = None

    @model_validator(mode="after")
    def _check_probability_sum(self) -> "OddsTable":
        if self.prob_sum_tolerance is None:
            return self  # registry applies the global default before/at load
        total = sum(o.probability for o in self.outcomes)
        if abs(total - 1.0) > self.prob_sum_tolerance:
            raise ValueError(
                f"odds table '{self.id}' probabilities sum to {total}, "
                f"not ~1.0 (tolerance {self.prob_sum_tolerance})"
            )
        return self


class OutcomeEv(BaseModel):
    result_key: str
    probability: float
    price: float | None
    contribution: float
    notes: str


class EvRow(BaseModel):
    table_id: str
    name: str
    ev_gross: float
    ev_net: float
    input_cost: float
    service_cost: float
    variance: float
    stddev: float
    per_outcome: list[OutcomeEv]
    liquidity: float
    confidence: float
    bankroll_note: str
    source: str
    deep_link: str | None
    unresolved_outcomes: int
    ts: datetime
