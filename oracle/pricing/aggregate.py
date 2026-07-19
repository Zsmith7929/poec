import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class AggResult:
    value: float
    sample_depth: int


def _reject_outliers(values: list[float], outlier_z: float) -> list[float]:
    if len(values) < 3:
        return values
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    mad = statistics.median(deviations) or 1e-9
    return [v for v in values if abs(v - med) / (1.4826 * mad) <= outlier_z]


def aggregate(values: list[float], percentile: float, outlier_z: float) -> AggResult:
    if not values:
        raise ValueError("cannot aggregate empty values")
    cleaned = _reject_outliers(sorted(values), outlier_z) or sorted(values)
    cleaned.sort()
    idx = min(int(percentile * (len(cleaned) - 1)), len(cleaned) - 1)
    return AggResult(value=cleaned[idx], sample_depth=len(cleaned))


def confidence(sample_depth: int, min_sample_depth: int, maturity_score: float) -> float:
    depth_factor = min(sample_depth / max(min_sample_depth, 1), 1.0)
    return max(0.0, min(1.0, 0.5 * depth_factor + 0.5 * maturity_score))
