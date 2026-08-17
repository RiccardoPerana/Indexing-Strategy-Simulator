"""
backtest.py

Runs a strategy against many independently generated price histories and
aggregates the results into summary statistics for the dashboard.
"""

from dataclasses import dataclass
from typing import List, Optional
import copy
import statistics

from price_generator import PriceGeneratorParams, generate_price_series
from simulator import run_simulation, SimulationResult
from strategy import Strategy


@dataclass
class BacktestResult:
    runs: List[SimulationResult]
    price_series_used: List[List[float]]

    @property
    def num_runs(self) -> int:
        return len(self.runs)

    def _values(self, extractor) -> List[float]:
        return [extractor(r) for r in self.runs]

    def summary(self) -> dict:
        # effective_ending_value (not ending_portfolio_value alone) so
        # this stays consistent with total_return_pct's own definition --
        # both now account for cash a strategy collected but never
        # actually invested, rather than that capital silently
        # disappearing from the "ending value" figure while still
        # depressing the return figure.
        endings = self._values(lambda r: r.effective_ending_value)
        invested = self._values(lambda r: r.total_cash_invested)
        returns = self._values(lambda r: r.total_return_pct)
        start_prices = self._values(lambda r: r.starting_price)
        end_prices = self._values(lambda r: r.ending_price)

        # Years per run, derived from the price series length. Used to
        # properly ANNUALIZE total return via compounding (CAGR-style):
        # (1 + total_return) ** (1/years) - 1. This is NOT the same as
        # averaging yearly % changes, which overstates growth due to
        # volatility drag -- annualizing must go through compounding.
        years = (len(self.price_series_used[0]) - 1) / 12
        annual_returns = [((1 + r) ** (1 / years) - 1) for r in returns]

        # Interquartile range: the middle 50% of outcomes. Pairs naturally
        # with median (both outlier-resistant), unlike std dev which is
        # built on the mean and gets dominated by the same rare bubble
        # runs that skew the average. Needs at least 4 runs for a
        # meaningful quartile split; fall back to min/max below that.
        if self.num_runs >= 4:
            q1, _, q3 = statistics.quantiles(returns, n=4, method="inclusive")
        else:
            q1, q3 = min(returns), max(returns)

        return {
            "num_runs": self.num_runs,
            "median_return_pct": statistics.median(returns) * 100,
            "avg_return_pct": statistics.mean(returns) * 100,  # kept: gap vs median is a useful skew signal
            "iqr_return_low_pct": q1 * 100,
            "iqr_return_high_pct": q3 * 100,
            "median_annual_return_pct": statistics.median(annual_returns) * 100,
            "median_cash_invested": statistics.median(invested),
            "median_ending_portfolio_value": statistics.median(endings),
            "starting_price": start_prices[0],  # fixed input, identical every run -- not an average
            "median_ending_price": statistics.median(end_prices),
            "median_max_drawdown_pct": statistics.median(self._values(lambda r: r.max_drawdown_pct)) * 100,
            "median_capital_efficiency_pct": statistics.median(
                self._values(lambda r: r.capital_efficiency_pct)) * 100,
        }

    def median_price_by_month(self) -> List[float]:
        """Median index price across all runs, for each month index.

        Unlike the average, this isn't dragged upward by a handful of
        bubble-heavy runs -- it's the "typical" run's price at each point
        in time, consistent with the median-first framing used everywhere
        else in the dashboard.
        """
        num_months = len(self.price_series_used[0])
        return [
            statistics.median(series[m] for series in self.price_series_used)
            for m in range(num_months)
        ]


def run_backtest(strategy: Strategy, price_params: PriceGeneratorParams,
                  starting_savings: float, monthly_income: float,
                  num_runs: int = 50,
                  reuse_prices: Optional[List[List[float]]] = None) -> BacktestResult:
    """
    Run `num_runs` simulations of `strategy` and aggregate the results.

    Args:
        strategy: strategy to test.
        price_params: parameters for generating each run's price history.
            Ignored if `reuse_prices` is supplied.
        starting_savings: initial cash pool for each run.
        monthly_income: monthly cash added to the pool for each run.
        num_runs: number of independent runs (default 50 per the brief).
        reuse_prices: if supplied, reuses this exact set of price series
            instead of generating new random ones -- this powers the
            "test against the data of the previous run" option.

    Returns:
        A BacktestResult aggregating all runs.
    """
    if reuse_prices is not None:
        price_series_list = reuse_prices
    else:
        price_series_list = []
        for i in range(num_runs):
            run_params = copy.copy(price_params)
            if price_params.seed is not None:
                # derive a distinct, reproducible seed per run
                run_params.seed = price_params.seed + i
            price_series_list.append(generate_price_series(run_params))

    results = []
    for prices in price_series_list:
        # Each run gets its own deep-copied strategy so stateful pieces
        # (like DepletingBaseBuy's patched fallback) never leak across runs.
        strategy_copy = copy.deepcopy(strategy)
        results.append(run_simulation(prices, strategy_copy, starting_savings, monthly_income))

    return BacktestResult(runs=results, price_series_used=price_series_list)


def generate_shared_price_data(price_params: PriceGeneratorParams, num_runs: int) -> List[List[float]]:
    """
    Generates one set of price series, using the EXACT same generation
    logic as run_backtest's own internal path (per-run seed offsets if a
    seed is set) -- factored out so compare_strategies() can generate it
    ONCE and pass the identical data to every strategy via reuse_prices,
    rather than each strategy silently getting its own random draw (which
    would make "compare all strategies" not actually a fair comparison).
    """
    price_series_list = []
    for i in range(num_runs):
        run_params = copy.copy(price_params)
        if price_params.seed is not None:
            run_params.seed = price_params.seed + i
        price_series_list.append(generate_price_series(run_params))
    return price_series_list


def compare_strategies(strategies: List[Strategy], price_params: PriceGeneratorParams,
                        starting_savings: float, monthly_income: float,
                        num_runs: int = 50,
                        shared_prices: Optional[List[List[float]]] = None) -> tuple:
    """
    Runs every strategy in `strategies` against the SAME price data (fair
    comparison -- generated once via generate_shared_price_data if
    `shared_prices` isn't already supplied), then ranks them by median
    total return, descending.

    Returns (rows, market_result):
        rows: a list of dicts, one per strategy, already sorted best-to-
            worst, each containing name, median_return_pct,
            median_annual_return_pct, median_cash_invested,
            median_ending_portfolio_value, median_max_drawdown_pct,
            median_capital_efficiency_pct (return on just the capital
            actually deployed, excluding idle cash from both sides of the
            ratio -- see SimulationResult.capital_efficiency_pct),
            return_gap_pct (best strategy's median return minus this
            one's -- always >= 0, and exactly 0 for the top-ranked
            strategy).
        market_result: the BacktestResult from whichever strategy happened
            to run first. This is NOT specific to that strategy -- every
            strategy here was run against the identical shared_prices, and
            a BacktestResult's price-based chart data (median_price_by_month
            etc.) depends only on price_series_used, not on any strategy's
            buying behavior -- so this is really just "the market data
            this whole comparison was based on," safe to chart regardless
            of which strategy happened to produce it. Exists so callers
            (e.g. the GUI's Compare All view) can show a price chart for
            the comparison as a whole, not tied to any one strategy.
    """
    if shared_prices is None:
        shared_prices = generate_shared_price_data(price_params, num_runs)

    rows = []
    market_result = None
    for strategy in strategies:
        result = run_backtest(strategy, price_params, starting_savings, monthly_income,
                               num_runs=num_runs, reuse_prices=shared_prices)
        if market_result is None:
            market_result = result
        s = result.summary()
        rows.append({
            "name": strategy.name,
            "median_return_pct": s["median_return_pct"],
            "median_annual_return_pct": s["median_annual_return_pct"],
            "median_cash_invested": s["median_cash_invested"],
            "median_ending_portfolio_value": s["median_ending_portfolio_value"],
            "median_max_drawdown_pct": s["median_max_drawdown_pct"],
            "median_capital_efficiency_pct": s["median_capital_efficiency_pct"],
        })

    rows.sort(key=lambda r: r["median_return_pct"], reverse=True)
    best_return = rows[0]["median_return_pct"] if rows else 0.0
    for row in rows:
        row["return_gap_pct"] = best_return - row["median_return_pct"]

    return rows, market_result
