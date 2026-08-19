"""
market_events.py

Defines the six key market events used throughout the simulation, and the
logic that classifies a single month's return into one of them.

Event thresholds (based on the previous month's percentage change):
    Crash        : return < -10%
    Extreme Loss : -10% <= return < -6%
    Loss         : -6% <= return < 0%
    Gain         : 0% <= return <= 6%
    Extreme Gain : 6% < return <= 10%
    Bubble       : return > 10%

BOUNDARY CONVENTION: a return landing exactly ON a threshold is assigned
to the MILDER of the two adjacent buckets, symmetrically in magnitude --
exactly -10% is an Extreme Loss (not a Crash) and exactly +10% is an
Extreme Gain (not a Bubble); exactly -6% is a Loss (not an Extreme Loss)
and exactly +6% is a Gain (not an Extreme Gain). classify_event's
comparison operators below implement this consistently. Two of the lines
above previously described the +6% boundary the other way round (Gain as
`< 6%`, Extreme Gain as `>= 6%`), which did not match the code; the code
was correct and the docstring has been corrected to match it, rather
than the reverse.

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
