import statistics


def maturity_signals(
    sample_depths: list[int],
    recent_values: list[list[float]],
    history_len: int,
) -> tuple[float, float, float, float]:
    median_depth = statistics.median(sample_depths) if sample_depths else 0.0
    vols: list[float] = []
    for series in recent_values:
        if len(series) >= 2 and statistics.mean(series):
            vols.append(statistics.pstdev(series) / statistics.mean(series))
    volatility = statistics.mean(vols) if vols else 1.0
    history_density = min(history_len / 30.0, 1.0)
    depth_norm = min(median_depth / 100.0, 1.0)
    score = max(
        0.0, min(1.0, 0.5 * depth_norm + 0.25 * (1 - min(volatility, 1.0)) + 0.25 * history_density)
    )
    return (median_depth, volatility, history_density, score)
