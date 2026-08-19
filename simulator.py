"""
simulator.py

Runs a single investing simulation: given one price history and a
Strategy, simulates month-by-month buying decisions and tracks the
resulting portfolio.
"""

from dataclasses import dataclass
from typing import List
from market_events import classify_event, MarketEvent
from strategy import Strategy, DepletingBaseBuy


@dataclass
class SimulationResult:
    """
    The full month-by-month history of one simulation run.

    NOTE: this deliberately does NOT retain per-month buy amounts or
    per-month shares purchased. Both were previously stored and never
    read by any consumer (dashboard, backtest, or GUI), costing ~2x600
    floats per run x N runs for nothing. If a "contribution history"
    chart is ever added, reinstate them here and append to them inside
    run_simulation's loop -- both values are already computed there, they
    are simply discarded now rather than accumulated.
    """
    prices: List[float]
    portfolio_value_by_month: List[float]
    cash_invested_by_month: List[float]  # cumulative, index-aligned with prices
    ending_uninvested_cash: float = 0.0  # cash collected but never actually invested, still held at the end

    @property
    def total_cash_invested(self) -> float:
        return self.cash_invested_by_month[-1]

    @property
    def ending_portfolio_value(self) -> float:
        return self.portfolio_value_by_month[-1]

    @property
    def total_capital_available(self) -> float:
        """
        Starting savings plus every monthly contribution collected over
        the whole simulation, regardless of whether it was ever actually
        invested. Equal to total_cash_invested + ending_uninvested_cash --
        this is the correct denominator for a capital-efficiency-aware
        return: using total_cash_invested alone (money ACTUALLY deployed)
        would make a strategy that leaves capital sitting idle look
        artificially better, since a smaller denominator inflates the
        percentage even though that idle capital earned nothing.
        """
        return self.total_cash_invested + self.ending_uninvested_cash

    @property
    def effective_ending_value(self) -> float:
        """
        Ending portfolio (market) value PLUS any cash collected but never
        actually invested -- the strategy's full ending wealth, not just
        the portion that was deployed into the market. A strategy that
        hoards cash instead of investing it doesn't lose that cash; it
        just isn't growing, which is exactly what this is meant to
        surface rather than hide.
        """
        return self.ending_portfolio_value + self.ending_uninvested_cash

    @property
    def total_return_pct(self) -> float:
        """
        (effective ending value - total capital available) / total
        capital available, as a fraction.

        Uses effective_ending_value / total_capital_available (both of
        which account for uninvested cash) rather than
        ending_portfolio_value / total_cash_invested (which would ignore
        it) -- so a strategy that systematically leaves money uninvested
        is correctly penalized for that capital's opportunity cost,
        instead of that money simply vanishing from both sides of the
        calculation. For a strategy that invests everything available
        every month, ending_uninvested_cash is ~0 and this produces
        (nearly) the same number as the simpler calculation would have --
        this change is specifically targeted at strategies that don't.
        """
        if self.total_capital_available == 0:
            return 0.0
        return (self.effective_ending_value - self.total_capital_available) / self.total_capital_available

    @property
    def capital_efficiency_pct(self) -> float:
        """
        (ending_portfolio_value - total_cash_invested) / total_cash_invested,
        as a fraction -- deliberately scope-consistent: BOTH sides
        restricted to money that was actually deployed into the market,
        excluding any idle uninvested cash entirely from both the
        numerator and the denominator.

        This answers a different question than total_return_pct: "how
        well did the money that WAS invested perform?", independent of
        how much capital the strategy chose to deploy in the first place.
        A strategy that deploys only half its available capital but
        follows the exact same buy pattern as one that deploys all of it
        will show the SAME capital_efficiency_pct as that fully-deployed
        strategy (confirmed with a real test: both landed on exactly
        22.9%) -- because the quality of ITS investment timing is
        identical; only the quantity of capital used differs, and that's
        what total_return_pct captures instead.

        IMPORTANT: do not naively mix scopes here (e.g. effective_ending_value
        in the numerator with total_cash_invested in the denominator) --
        that was tried and produced a strategy that hoards HALF its
        capital showing a 122.9% ratio against a fully-invested
        strategy's 22.9%, a 5x-better-looking number for the strategy
        that actually used its capital worse. Idle cash sitting unchanged
        must be excluded from BOTH sides together, or it gets "free
        credit" in the numerator without being charged for in the
        denominator.
        """
        if self.total_cash_invested == 0:
            return 0.0
        return (self.ending_portfolio_value - self.total_cash_invested) / self.total_cash_invested

    @property
    def max_drawdown_pct(self) -> float:
        """
        The largest peak-to-trough decline in PORTFOLIO VALUE (not the
        underlying index price) over the whole simulation, as a fraction
        (always <= 0; 0.0 means the portfolio never fell below a prior
        high). Computed on portfolio value rather than price because this
        is meant for comparing STRATEGIES -- a strategy's drawdown
        reflects both market moves and its own buying behavior, which is
        exactly what differs between strategies tested against identical
        price data.

        Note: since portfolio value starts at 0 and grows via ongoing
        contributions, a naive early "recovery" from a dip could in
        principle be new money rather than market recovery -- this uses
        the standard peak-to-trough definition regardless, since that's
        what "maximum drawdown" conventionally means, but it's worth
        knowing this isn't purely a market-return metric for a
        contribution-based strategy.
        """
        peak = 0.0
        worst = 0.0
        for v in self.portfolio_value_by_month:
            if v > peak:
                peak = v
            elif peak > 0:
                dd = (v - peak) / peak
                if dd < worst:
                    worst = dd
        return worst

    @property
    def starting_price(self) -> float:
        return self.prices[0]

    @property
    def ending_price(self) -> float:
        return self.prices[-1]


def run_simulation(prices: List[float], strategy: Strategy,
                    starting_savings: float, monthly_income: float) -> SimulationResult:
    """
    Simulate one full run of a strategy against one price history.

    Cash model:
        - `starting_savings` is a lump sum available from month 0.
        - `monthly_income` is added to the available cash pool every month,
          BEFORE that month's buy decision is made.
        - The strategy decides the intended buy amount; it is always capped
          at whatever cash is actually available that month (you can never
          invest money you don't have -- including "buy as much as
          possible" strategies, which use float('inf') as a sentinel that
          this cap resolves safely).

    Args:
        prices: monthly price series; prices[0] is the starting price,
            prices[i] is the price at the end of month i.
        strategy: the Strategy to apply. NOTE: pass a fresh/copied instance
            per run if the strategy has stateful pieces (see backtest.py,
            which handles this automatically).
        starting_savings: initial cash pool (e.g. an emergency-fund-style lump sum).
        monthly_income: recurring cash added to the pool each month.

    Returns:
        A SimulationResult with the full month-by-month history.
    """
    if isinstance(strategy.base_buy_override, DepletingBaseBuy):
        # Presets are defined independent of run-specific parameters, so we
        # patch the fallback level to this run's real monthly income here.
        strategy.base_buy_override.fallback_amount = monthly_income

    available_cash = starting_savings
    total_shares = 0.0
    cumulative_invested = 0.0
    loss_streak = 0
    gain_streak = 0
    running_peak_price = prices[0]  # tracks the all-time high seen so far, for drawdown_from_peak triggers

    portfolio_value_by_month: List[float] = [total_shares * prices[0]]  # month 0
    cash_invested_by_month: List[float] = [cumulative_invested]

    num_months = len(prices) - 1  # prices includes the month-0 starting price

    for month in range(1, num_months + 1):
        available_cash += monthly_income

        prev_price = prices[month - 1]
        curr_price = prices[month]
        monthly_return = (curr_price - prev_price) / prev_price
        event = classify_event(monthly_return)

        # Update the running peak with this month's price BEFORE computing
        # drawdown, so a month that itself sets a new all-time high always
        # reports drawdown=0.0 rather than comparing against a stale peak.
        running_peak_price = max(running_peak_price, curr_price)
        drawdown_from_peak = (curr_price - running_peak_price) / running_peak_price if running_peak_price > 0 else 0.0

        # update consecutive gain/loss streak counters
        if event in (MarketEvent.LOSS, MarketEvent.EXTREME_LOSS, MarketEvent.CRASH):
            loss_streak += 1
            gain_streak = 0
        else:
            gain_streak += 1
            loss_streak = 0

        intended_buy = strategy.compute_buy_amount(
            base_buy=monthly_income,
            event=event,
            monthly_return=monthly_return,
            loss_streak=loss_streak,
            gain_streak=gain_streak,
            available_cash=available_cash,
            drawdown_from_peak=drawdown_from_peak,
        )

        actual_buy = max(0.0, min(intended_buy, available_cash))
        shares_bought = actual_buy / curr_price if curr_price > 0 else 0.0

        available_cash -= actual_buy
        total_shares += shares_bought
        cumulative_invested += actual_buy

        portfolio_value_by_month.append(total_shares * curr_price)
        cash_invested_by_month.append(cumulative_invested)

    return SimulationResult(
        prices=prices,
        portfolio_value_by_month=portfolio_value_by_month,
        cash_invested_by_month=cash_invested_by_month,
        ending_uninvested_cash=available_cash,
    )
