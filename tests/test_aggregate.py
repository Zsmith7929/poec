from hypothesis import given
from hypothesis import strategies as st

from oracle.pricing.aggregate import aggregate, confidence


def test_aggregate_rejects_single_outlier() -> None:
    values = [10.0, 10.5, 9.8, 10.2, 10.1, 1000.0]  # last is a spike
    res = aggregate(values, percentile=0.15, outlier_z=3.0)
    assert res.value < 20.0
    assert res.sample_depth == 5  # outlier removed


def test_aggregate_never_returns_raw_minimum() -> None:
    values = [1.0, 5.0, 5.0, 5.0, 5.0]
    res = aggregate(values, percentile=0.15, outlier_z=3.0)
    assert res.value == 5.0  # raw minimum 1.0 must be rejected as an outlier


@given(st.floats(min_value=0, max_value=1), st.integers(0, 100), st.floats(0, 1))
def test_confidence_in_unit_interval(_p: float, depth: int, mat: float) -> None:
    c = confidence(depth, min_sample_depth=5, maturity_score=mat)
    assert 0.0 <= c <= 1.0
