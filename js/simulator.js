/*
 * simulator.js
 *
 * Runs a single investing simulation: given one price history and a
 * Strategy, simulates month-by-month buying decisions and tracks the
 * resulting portfolio.
 */

class SimulationResult {
  constructor({ prices, portfolioValueByMonth, cashInvestedByMonth, endingUninvestedCash = 0.0 }) {
    this.prices = prices;
    this.portfolioValueByMonth = portfolioValueByMonth;
    this.cashInvestedByMonth = cashInvestedByMonth;
    this.endingUninvestedCash = endingUninvestedCash;
  }

  get totalCashInvested() {
    return this.cashInvestedByMonth[this.cashInvestedByMonth.length - 1];
  }

  get endingPortfolioValue() {
    return this.portfolioValueByMonth[this.portfolioValueByMonth.length - 1];
  }

  // Starting savings + every monthly contribution collected, regardless
  // of whether it was ever actually invested.
  get totalCapitalAvailable() {
    return this.totalCashInvested + this.endingUninvestedCash;
  }

  // Ending portfolio (market) value plus any cash collected but never
  // actually invested -- the strategy's full ending wealth.
  get effectiveEndingValue() {
    return this.endingPortfolioValue + this.endingUninvestedCash;
  }

  get totalReturnPct() {
    const capital = this.totalCapitalAvailable;
    if (capital === 0) return 0.0;
    return (this.effectiveEndingValue - capital) / capital;
  }

  // Scope-consistent: both sides restricted to money actually deployed
  // into the market, excluding idle uninvested cash from both sides.
  get capitalEfficiencyPct() {
    if (this.totalCashInvested === 0) return 0.0;
    return (this.endingPortfolioValue - this.totalCashInvested) / this.totalCashInvested;
  }

  get maxDrawdownPct() {
    let peak = 0.0;
    let worst = 0.0;
    for (const v of this.portfolioValueByMonth) {
      if (v > peak) {
        peak = v;
      } else if (peak > 0) {
        const dd = (v - peak) / peak;
        if (dd < worst) worst = dd;
      }
    }
    return worst;
  }

  get startingPrice() {
    return this.prices[0];
  }

  get endingPrice() {
    return this.prices[this.prices.length - 1];
  }
}

function runSimulation(prices, strategy, startingSavings, monthlyIncome) {
  if (strategy.baseBuyOverride instanceof DepletingBaseBuy) {
    // Presets are defined independent of run-specific parameters, so the
    // fallback level is patched to this run's real monthly income here.
    strategy.baseBuyOverride.fallbackAmount = monthlyIncome;
  }

  let availableCash = startingSavings;
  let totalShares = 0.0;
  let cumulativeInvested = 0.0;
  let lossStreak = 0;
  let gainStreak = 0;
  let runningPeakPrice = prices[0];

  const portfolioValueByMonth = [totalShares * prices[0]];
  const cashInvestedByMonth = [cumulativeInvested];

  const numMonths = prices.length - 1;

  for (let month = 1; month <= numMonths; month++) {
    availableCash += monthlyIncome;

    const prevPrice = prices[month - 1];
    const currPrice = prices[month];
    const monthlyReturn = (currPrice - prevPrice) / prevPrice;
    const event = classifyEvent(monthlyReturn);

    runningPeakPrice = Math.max(runningPeakPrice, currPrice);
    const drawdownFromPeak =
      runningPeakPrice > 0 ? (currPrice - runningPeakPrice) / runningPeakPrice : 0.0;

    if (event === MarketEvent.LOSS || event === MarketEvent.EXTREME_LOSS || event === MarketEvent.CRASH) {
      lossStreak += 1;
      gainStreak = 0;
    } else {
      gainStreak += 1;
      lossStreak = 0;
    }

    const intendedBuy = strategy.computeBuyAmount(monthlyIncome, {
      event,
      monthlyReturn,
      lossStreak,
      gainStreak,
      drawdownFromPeak,
      availableCash,
      prices,
      monthIndex: month,
      price: currPrice,
    });

    const actualBuy = Math.max(0.0, Math.min(intendedBuy, availableCash));
    const sharesBought = currPrice > 0 ? actualBuy / currPrice : 0.0;

    availableCash -= actualBuy;
    totalShares += sharesBought;
    cumulativeInvested += actualBuy;

    portfolioValueByMonth.push(totalShares * currPrice);
    cashInvestedByMonth.push(cumulativeInvested);
  }

  return new SimulationResult({
    prices,
    portfolioValueByMonth,
    cashInvestedByMonth,
    endingUninvestedCash: availableCash,
  });
}
