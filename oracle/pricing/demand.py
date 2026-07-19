"""Demand / tradeability classification. See ADR-0005.

poe.ninja gives different signals per feed, and they must not be conflated:

- Exchange feed (currency, fragments): `sample_depth` is real trade VOLUME — a genuine
  demand signal.
- Stash feed (uniques, base types, gems): `sample_depth` is the LISTING COUNT (supply,
  not demand). Demand must instead be judged from how many observations back the price
  (`observations`) and whether the price is moving (`trend`). A high listing count with
  a price built off 1-2 stale, non-moving listings is the classic mirage-margin case.
"""

from typing import Literal

DemandLabel = Literal["active", "thin", "unknown"]

# A price is considered "moving" (i.e. trades are actually happening) when its sparkline
# has shifted at least this many percent over the window.
_TREND_EPSILON = 1.0


def demand_label(
    *,
    sample_depth: int,
    observations: int | None,
    trend: float | None,
    min_depth: int,
) -> DemandLabel:
    """Classify tradeability. `observations is None` marks an exchange (volume) price;
    otherwise it is a stash (listing-count) price and supply must not stand in for
    demand."""
    if observations is None:
        # Exchange price: sample_depth IS volume.
        return "active" if sample_depth >= min_depth else "thin"
    # Stash price: sample_depth is supply. Judge from sample size + movement.
    if observations >= min_depth or abs(trend or 0.0) >= _TREND_EPSILON:
        return "active"
    return "thin"
