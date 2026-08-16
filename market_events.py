"""
market_events.py

Defines the six key market events used throughout the simulation, and the
logic that classifies a single month's return into one of them.

Event thresholds (based on the previous month's percentage change):
    Crash        : return < -10%
    Extreme Loss : -10% <= return < -6%
    Loss         : -6% <= return < 0%
    Gain         : 0% <= return < 6%
    Extreme Gain : 6% <= return <= 10%
    Bubble       : return > 10%

NOTE ON ASSUMPTION: the brief specifies "Gain: 0 to +5%" and "Extreme Gain:
6 to 10%" (and symmetrically for losses), which leaves the 5%-6% band
undefined. We resolved that gap by extending Gain/Loss up to 6%, so every
possible return maps to exactly one event with no overlaps or holes. If you
want a different boundary, this is the only place you need to change it.
"""

from enum import Enum


class MarketEvent(Enum):
    CRASH = "Crash"
    EXTREME_LOSS = "Extreme Loss"
    LOSS = "Loss"
    GAIN = "Gain"
    EXTREME_GAIN = "Extreme Gain"
    BUBBLE = "Bubble"


def classify_event(monthly_return: float) -> MarketEvent:
    """
    Classify a single month's percentage return into a MarketEvent.

    Args:
        monthly_return: fractional return for the month, e.g. -0.07 for -7%.

    Returns:
        The MarketEvent bucket the return falls into.
    """
    if monthly_return < -0.10:
        return MarketEvent.CRASH
    elif monthly_return < -0.06:
        return MarketEvent.EXTREME_LOSS
    elif monthly_return < 0:
        return MarketEvent.LOSS
    elif monthly_return <= 0.06:
        return MarketEvent.GAIN
    elif monthly_return <= 0.10:
        return MarketEvent.EXTREME_GAIN
    else:
        return MarketEvent.BUBBLE
