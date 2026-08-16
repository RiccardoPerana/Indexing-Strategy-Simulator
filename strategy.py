"""
strategy.py

Defines the rule-based strategy engine. A Strategy is a data structure
that decides, month by month, how much to invest given the current market
event and recent history. Every strategy in the project brief reduces to
a combination of these rules -- no strategy requires custom code, only
configuration. See presets.py for all 9 examples from the brief built
this way.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from market_events import MarketEvent


@dataclass
class Trigger:
    """
    Describes the condition under which a rule fires.

    type:
        "event"             -> fires when the current month's MarketEvent
                                equals `event`
        "sequential_loss"   -> fires when there have been `streak` or more
                                consecutive losing months (Loss/ExtremeLoss/
                                Crash), including the current one
        "sequential_gain"   -> fires when there have been `streak` or more
                                consecutive gaining months (Gain/ExtremeGain/
                                Bubble), including the current one
        "return_threshold"  -> fires when the current month's return
                                satisfies `operator` against `value`
                                (operator in "lte", "lt", "gte", "gt")
        "drawdown_from_peak" -> fires when the current price is at or below
                                `value` (a negative fraction, e.g. -0.20)
                                relative to the highest price reached so
                                far in the simulation -- e.g. value=-0.20
                                fires once the index is 20%+ off its
                                running all-time high. Distinct from the
                                single-month event triggers: this tracks
                                the whole simulation's history, not just
                                the most recent month.
    """
    type: str
    event: Optional[MarketEvent] = None
    streak: Optional[int] = None
    operator: Optional[str] = None
    value: Optional[float] = None

    def matches(self, event: MarketEvent, monthly_return: float,
                loss_streak: int, gain_streak: int,
                drawdown_from_peak: float = 0.0) -> bool:
        if self.type == "event":
            return event == self.event
        if self.type == "sequential_loss":
            return loss_streak >= (self.streak or 1)
        if self.type == "sequential_gain":
            return gain_streak >= (self.streak or 1)
        if self.type == "return_threshold":
            ops = {
                "lte": lambda r, v: r <= v,
                "lt": lambda r, v: r < v,
                "gte": lambda r, v: r >= v,
                "gt": lambda r, v: r > v,
            }
            return ops[self.operator](monthly_return, self.value)
        if self.type == "drawdown_from_peak":
            return drawdown_from_peak <= self.value
        raise ValueError(f"Unknown trigger type: {self.type}")


@dataclass
class Action:
    """
    Describes what happens to the buy amount when a rule's trigger matches.

    type:
        "multiply"          -> buy = base_buy * value
        "set_fixed"         -> buy = value (use float('inf') for "buy as much as possible")
        "add_fixed"         -> buy = base_buy + value
        "skip"              -> buy = 0
        "scale_with_streak" -> buy = base_buy * multiplier, where the
                                multiplier grows with how long the current
                                streak has run:
                                    multiplier = start + increment * (streak - 1)
                                capped at `cap` if given. Pairs with a
                                "sequential_loss"/"sequential_gain" trigger
                                set to streak=1 (i.e. "active from the
                                first month of the streak onward"), so ONE
                                rule handles escalation instead of stacking
                                several fixed-multiplier rules by hand.
                                Example: start=1, increment=1, cap=5 gives
                                exactly "buy normally, then 2x, 3x, 4x...
                                capped at 5x" for a growing loss streak.
    """
    type: str
    value: Optional[float] = None
    start: float = 1.0     # only used by "scale_with_streak"
    increment: float = 0.0  # only used by "scale_with_streak"
    cap: Optional[float] = None  # only used by "scale_with_streak"

    def apply(self, base_buy: float, streak: int = 1) -> float:
        if self.type == "multiply":
            return base_buy * self.value
        if self.type == "set_fixed":
            return self.value
        if self.type == "add_fixed":
            return base_buy + self.value
        if self.type == "skip":
            return 0.0
        if self.type == "scale_with_streak":
            multiplier = self.start + self.increment * (streak - 1)
            if self.cap is not None:
                multiplier = min(multiplier, self.cap)
            return base_buy * multiplier
        raise ValueError(f"Unknown action type: {self.type}")


@dataclass
class Rule:
    trigger: Trigger
    action: Action


@dataclass
class DepletingBaseBuy:
    """
    Implements the "start high, then drop to income level" style strategy.
    While available cash allows buying `preferred_amount`, that amount is
    used as the base buy. Once available cash can no longer sustain it,
    the base buy falls back to `fallback_amount` (typically monthly income).
    """
    preferred_amount: float
    fallback_amount: float

    def compute(self, available_cash: float) -> float:
        return self.preferred_amount if available_cash >= self.preferred_amount \
            else self.fallback_amount


@dataclass
class Strategy:
    name: str
    rules: List[Rule] = field(default_factory=list)
    base_buy_override: Optional[DepletingBaseBuy] = None
    allow_selling: bool = False  # reserved for v2 (moving-average sell rules)
    description: str = ""  # short human-readable summary, shown alongside results

    def compute_buy_amount(self, base_buy: float, event: MarketEvent,
                            monthly_return: float, loss_streak: int,
                            gain_streak: int, available_cash: float,
                            drawdown_from_peak: float = 0.0) -> float:
        """
        Determine how much to invest this month.

        Every matching rule is applied IN ORDER, each one transforming the
        running buy amount before the next rule sees it -- rules compose
        rather than compete. This is what lets a per-event multiplier and
        a streak-escalation rule work together naturally: e.g. a "Loss"
        multiplier of 1.5x combined with a loss-streak escalation of
        +1x/month doesn't require choosing one or the other -- the
        escalation multiplies on top of the already-adjusted amount, so a
        3-month loss streak with both configured buys 1.5x * 3x = 4.5x the
        base. If no rule matches, the (possibly overridden) base buy is
        used unchanged.

        drawdown_from_peak: current price's fractional distance below the
            running all-time-high seen so far this simulation (always <= 0;
            0.0 means at a new peak). Defaults to 0.0 so callers/strategies
            that don't use "drawdown_from_peak" triggers are unaffected.
        """
        amount = base_buy
        if self.base_buy_override is not None:
            amount = self.base_buy_override.compute(available_cash)

        for rule in self.rules:
            if rule.trigger.matches(event, monthly_return, loss_streak, gain_streak,
                                     drawdown_from_peak=drawdown_from_peak):
                # Give the action whichever streak its trigger cares about,
                # so "scale_with_streak" can compute the right multiplier.
                # Defaults to 1 (no scaling effect) for triggers that
                # aren't streak-based at all.
                relevant_streak = 1
                if rule.trigger.type == "sequential_loss":
                    relevant_streak = loss_streak
                elif rule.trigger.type == "sequential_gain":
                    relevant_streak = gain_streak
                amount = rule.action.apply(amount, streak=relevant_streak)

        return max(0.0, amount)  # never invest a negative amount
