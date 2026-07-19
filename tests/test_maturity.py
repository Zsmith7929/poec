from oracle.pricing.maturity import maturity_signals


def test_thin_data_scores_lower_than_rich_data() -> None:
    thin = maturity_signals([1, 2, 1], [[10.0, 90.0]], history_len=1)
    rich = maturity_signals([200, 300, 250], [[10.0, 10.1, 10.0]], history_len=30)
    assert rich[3] > thin[3]  # score
