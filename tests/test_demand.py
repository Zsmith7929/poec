from oracle.pricing.demand import demand_label


def test_exchange_volume_drives_demand() -> None:
    # observations=None marks an exchange price; sample_depth IS volume.
    assert demand_label(sample_depth=1000, observations=None, trend=None, min_depth=5) == "active"
    assert demand_label(sample_depth=2, observations=None, trend=None, min_depth=5) == "thin"


def test_stash_thin_when_few_observations_and_flat() -> None:
    # The mirage case: lots listed (supply) but priced off 2 non-moving observations.
    assert demand_label(sample_depth=50, observations=2, trend=0.0, min_depth=5) == "thin"


def test_stash_supply_alone_does_not_make_it_active() -> None:
    # High listing count (supply) must NOT read as demand (ADR-0005).
    assert demand_label(sample_depth=500, observations=1, trend=0.0, min_depth=5) == "thin"


def test_stash_active_with_enough_observations() -> None:
    assert demand_label(sample_depth=50, observations=61, trend=0.0, min_depth=5) == "active"


def test_stash_active_when_price_is_moving() -> None:
    # Movement implies trades are happening even if observation count is low.
    assert demand_label(sample_depth=10, observations=2, trend=23.8, min_depth=5) == "active"
    assert demand_label(sample_depth=10, observations=2, trend=-12.0, min_depth=5) == "active"
