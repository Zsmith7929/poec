from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from oracle.config import T2Settings, load_settings
from oracle.scanner.models import PriceRef
from oracle.scanner.t2_models import EvRow, OddsTable, Outcome, OutcomeEv


def _ref(key: str) -> PriceRef:
    return PriceRef(category="UniqueAccessory", key=key)


def test_outcome_probability_bounds() -> None:
    Outcome(result=_ref("X"), probability=0.5)
    with pytest.raises(ValidationError):
        Outcome(result=_ref("X"), probability=1.5)
    with pytest.raises(ValidationError):
        Outcome(result=_ref("X"), probability=-0.1)


def test_outcome_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        Outcome(result=_ref("X"), probability=0.5, bogus=1)  # type: ignore[call-arg]


def test_oddstable_valid_sum_ok() -> None:
    t = OddsTable(
        id="t",
        name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        outcomes=[
            Outcome(result=_ref("A"), probability=0.25),
            Outcome(result=_ref("B"), probability=0.25),
            Outcome(result=_ref("C"), probability=0.5),
        ],
        source="https://example.com/odds",
        prob_sum_tolerance=1e-6,
    )
    assert len(t.outcomes) == 3
    assert t.enabled is True
    assert t.service_cost == 0.0


def test_oddstable_bad_sum_fails_loud() -> None:
    with pytest.raises(ValidationError):
        OddsTable(
            id="t",
            name="T",
            input=PriceRef(category="Currency", key="Vaal Orb"),
            outcomes=[
                Outcome(result=_ref("A"), probability=0.25),
                Outcome(result=_ref("B"), probability=0.25),
            ],  # sums to 0.5
            source="https://example.com/odds",
            prob_sum_tolerance=1e-6,
        )


def test_oddstable_within_tolerance_ok() -> None:
    # 0.333*3 = 0.999; tolerance 0.01 accepts it.
    OddsTable(
        id="t",
        name="T",
        input=PriceRef(category="Currency", key="Vaal Orb"),
        outcomes=[Outcome(result=_ref(k), probability=0.333) for k in "ABC"],
        source="https://example.com/odds",
        prob_sum_tolerance=0.01,
    )


def test_oddstable_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        OddsTable(
            id="t",
            name="T",
            input=PriceRef(category="Currency", key="Vaal Orb"),
            outcomes=[Outcome(result=_ref("A"), probability=1.0)],
            source="s",
            bogus=1,  # type: ignore[call-arg]
        )


def test_evrow_and_outcome_ev_construct() -> None:
    row = EvRow(
        table_id="t",
        name="T",
        ev_gross=100.0,
        ev_net=90.0,
        input_cost=8.0,
        service_cost=2.0,
        variance=25.0,
        stddev=5.0,
        per_outcome=[
            OutcomeEv(result_key="A", probability=1.0, price=100.0, contribution=100.0, notes="")
        ],
        liquidity=40.0,
        confidence=0.8,
        bankroll_note="10 attempts at 10c each",
        source="ninja:x",
        deep_link=None,
        unresolved_outcomes=0,
        ts=datetime.now(tz=UTC),
    )
    assert row.ev_net == 90.0
    assert row.per_outcome[0].price == 100.0


def test_t2_settings_loaded_from_config() -> None:
    settings = load_settings()
    assert isinstance(settings.t2, T2Settings)
    assert settings.t2.prob_sum_tolerance > 0.0
    assert settings.t2.mc_trials >= 1
    assert settings.t2.mc_seed >= 0
