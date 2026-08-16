"""
presets.py

Ready-made strategies covering every example from the project brief.
Each one is built entirely out of Strategy/Rule/Trigger/Action objects --
no custom code paths per strategy -- which proves the rule engine is
expressive enough to cover the full requested strategy space.

NOTE: "Buy and sell according to the moving average" is intentionally
NOT included here -- selling was scoped as a v2 add-on. The Strategy
class already has an `allow_selling` flag reserved for it.

Naming convention: each Strategy's `.name` is a clean, professional label
with no embedded parameter values; the specific numbers (multipliers,
thresholds, streak lengths) live in `.description` instead, where they
add real information without cluttering the label. This also keeps the
name shown in ALL_PRESETS (used to populate the GUI dropdown) identical
to the name the built Strategy actually reports in the results panel --
previously these could differ for the parametrized presets.
"""

from market_events import MarketEvent
from strategy import Strategy, Rule, Trigger, Action, DepletingBaseBuy


def buy_max_every_month() -> Strategy:
    """Invest all available cash every month, regardless of market conditions."""
    return Strategy(
        name="Full Capital Deployment",
        description="Invests all available capital every month, in both rising "
                     "and falling markets, with no attempt at market timing. The "
                     "most aggressive strategy in this set.",
        rules=[
            Rule(Trigger(type="event", event=e), Action(type="set_fixed", value=float("inf")))
            for e in MarketEvent
        ],
    )


def start_high_then_income() -> Strategy:
    """Buy 500€/month while savings allow it, then drop to monthly income level."""
    return Strategy(
        name="Front-Loaded Contribution",
        description="Contributes \u20ac500 per month for as long as available savings "
                     "permit, then reduces to the standard monthly contribution level "
                     "thereafter. This switch is driven by available savings, not "
                     "market performance.",
        # fallback_amount is patched to the run's real monthly_income
        # automatically by simulator.run_simulation()
        base_buy_override=DepletingBaseBuy(preferred_amount=500.0, fallback_amount=0.0),
    )


def multiply_on_sequential_losses(multiplier: float = 2.0, streak: int = 2) -> Strategy:
    """Multiply the buy after `streak` consecutive losing months."""
    return Strategy(
        name="Sequential Loss Amplification",
        description=f"Increases the monthly contribution by a factor of {multiplier}x "
                     f"once the market has declined for {streak} consecutive months. "
                     f"The standard contribution applies at all other times, and "
                     f"resumes as soon as the losing streak ends.",
        rules=[
            Rule(Trigger(type="sequential_loss", streak=streak),
                 Action(type="multiply", value=multiplier)),
        ],
    )


def decrease_on_sequential_gains(multiplier: float = 0.5, streak: int = 2) -> Strategy:
    """Decrease the buy after `streak` consecutive gaining months."""
    return Strategy(
        name="Sequential Gain Moderation",
        description=f"Reduces the monthly contribution to a factor of {multiplier}x "
                     f"once the market has advanced for {streak} consecutive months. "
                     f"The standard contribution applies at all other times, and "
                     f"resumes as soon as the winning streak ends.",
        rules=[
            Rule(Trigger(type="sequential_gain", streak=streak),
                 Action(type="multiply", value=multiplier)),
        ],
    )


def max_buy_on_crash() -> Strategy:
    """Buy as much as possible during a Crash; base buy otherwise."""
    return Strategy(
        name="Crash-Triggered Maximum Allocation",
        description="Allocates the maximum available capital during a Crash month "
                     "(a decline exceeding 10%); the standard contribution applies "
                     "in all other months.",
        rules=[
            Rule(Trigger(type="event", event=MarketEvent.CRASH),
                 Action(type="set_fixed", value=float("inf"))),
        ],
    )


def max_buy_on_any_loss() -> Strategy:
    """Buy as much as possible on any losing month (Loss / Extreme Loss / Crash)."""
    return Strategy(
        name="Broad Downturn Accumulation",
        description="Allocates the maximum available capital during any month of "
                     "decline \u2014 Loss, Extreme Loss, or Crash. The standard "
                     "contribution applies during months of market gains.",
        rules=[
            Rule(Trigger(type="event", event=MarketEvent.CRASH), Action(type="set_fixed", value=float("inf"))),
            Rule(Trigger(type="event", event=MarketEvent.EXTREME_LOSS), Action(type="set_fixed", value=float("inf"))),
            Rule(Trigger(type="event", event=MarketEvent.LOSS), Action(type="set_fixed", value=float("inf"))),
        ],
    )


def double_on_loss_over_5pct() -> Strategy:
    """Double the buy if the market lost more than 5% last month."""
    return Strategy(
        name="Threshold-Based Loss Response",
        description="Doubles the monthly contribution whenever the market has "
                     "declined by more than 5% over the preceding month \u2014 a "
                     "lower threshold than a full Crash designation. The standard "
                     "contribution applies in all other months.",
        rules=[
            Rule(Trigger(type="return_threshold", operator="lte", value=-0.05),
                 Action(type="multiply", value=2.0)),
        ],
    )


def half_on_gain_over_10pct() -> Strategy:
    """Halve the buy if the market gained more than 10% last month (Bubble)."""
    return Strategy(
        name="Overextension Moderation",
        description="Reduces the monthly contribution by half following a Bubble "
                     "month (a gain exceeding 10%). The standard contribution "
                     "applies in all other months.",
        rules=[
            Rule(Trigger(type="event", event=MarketEvent.BUBBLE),
                 Action(type="multiply", value=0.5)),
        ],
    )


def momentum_chasing(multiplier: float = 1.5, streak: int = 2) -> Strategy:
    """Increase the buy after `streak` consecutive gaining months -- the mirror image of decrease_on_sequential_gains."""
    return Strategy(
        name="Momentum Chasing",
        description=f"Increases the monthly contribution by a factor of {multiplier}x "
                     f"once the market has advanced for {streak} consecutive months, "
                     f"treating sustained strength as a signal to increase exposure "
                     f"rather than moderate it. The standard contribution applies at "
                     f"all other times, and resumes as soon as the winning streak ends.",
        rules=[
            Rule(Trigger(type="sequential_gain", streak=streak),
                 Action(type="multiply", value=multiplier)),
        ],
    )


def drawdown_buying(multiplier: float = 2.0, drawdown_threshold: float = -0.20) -> Strategy:
    """Increase the buy whenever price is drawdown_threshold or more below the running all-time high."""
    return Strategy(
        name="Drawdown Accumulation",
        description=f"Increases the monthly contribution by a factor of {multiplier}x "
                     f"whenever the index is trading at least "
                     f"{abs(drawdown_threshold) * 100:.0f}% below the highest price "
                     f"reached so far in the simulation. The standard contribution "
                     f"applies once the index recovers to within "
                     f"{abs(drawdown_threshold) * 100:.0f}% of that high.",
        rules=[
            Rule(Trigger(type="drawdown_from_peak", value=drawdown_threshold),
                 Action(type="multiply", value=multiplier)),
        ],
    )


def dollar_cost_average() -> Strategy:
    """Baseline: invest the same fixed amount every month, no reaction to events."""
    return Strategy(
        name="Standard Dollar-Cost Averaging",
        description="Contributes a fixed amount each month regardless of market "
                     "conditions. Serves as the baseline against which all other "
                     "strategies in this set are evaluated.",
        rules=[],
    )


def escalate_on_loss_streak(increment: float = 1.0, cap: float = 5.0) -> Strategy:
    """
    Buy normally on the first losing month, then escalate the multiplier by
    `increment` for every additional consecutive losing month, capped at
    `cap`x. With the defaults: month 1 of a loss streak = 1x, month 2 = 2x,
    month 3 = 3x, month 4 = 4x, capped at 5x from month 5 onward -- "get
    the most out of a crash" as it deepens, without buying an unbounded
    amount if the losing streak runs on for a very long time.
    """
    return Strategy(
        name="Progressive Downturn Accumulation",
        description=f"Begins at the standard contribution level and increases it by "
                     f"{increment}x for every additional consecutive losing month, up "
                     f"to a maximum of {cap}x. The multiplier resets to the standard "
                     f"level as soon as a gaining month breaks the losing streak.",
        rules=[
            Rule(Trigger(type="sequential_loss", streak=1),
                 Action(type="scale_with_streak", start=1.0, increment=increment, cap=cap)),
        ],
    )


# key -> (display name, zero-arg factory function)
# Display names here are identical to each factory's Strategy.name, so the
# GUI dropdown and the results panel always show the same label.
ALL_PRESETS = {
    "1": ("Full Capital Deployment", buy_max_every_month),
    "2": ("Front-Loaded Contribution", start_high_then_income),
    "3": ("Sequential Loss Amplification", multiply_on_sequential_losses),
    "4": ("Sequential Gain Moderation", decrease_on_sequential_gains),
    "5": ("Crash-Triggered Maximum Allocation", max_buy_on_crash),
    "6": ("Broad Downturn Accumulation", max_buy_on_any_loss),
    "7": ("Threshold-Based Loss Response", double_on_loss_over_5pct),
    "8": ("Overextension Moderation", half_on_gain_over_10pct),
    "9": ("Standard Dollar-Cost Averaging", dollar_cost_average),
    "10": ("Progressive Downturn Accumulation", escalate_on_loss_streak),
    "11": ("Momentum Chasing", momentum_chasing),
    "12": ("Drawdown Accumulation", drawdown_buying),
}
