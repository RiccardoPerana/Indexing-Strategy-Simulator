/*
 * backtest.js
 *
 * Runs a strategy against many independently generated price histories
 * and aggregates the results, plus compareStrategies() for the
 * "Compare All" table.
 */

function median(values) {
  const s = [...values].sort((a, b) => a - b);
  const n = s.length;
  const mid = Math.floor(n / 2);
  return n % 2 !== 0 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function mean(values) {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

// Port of Python's statistics.quantiles(data, n=4, method="inclusive").
function quantilesInclusive(values, n = 4) {
  const data = [...values].sort((a, b) => a - b);
  const m = data.length - 1;
  const result = [];
  for (let i = 1; i < n; i++) {
    const im = i * m;
    const j = Math.floor(im / n);
    const delta = im - j * n;
    const next = j + 1 < data.length ? data[j + 1] : data[j];
    result.push((data[j] * (n - delta) + next * delta) / n);
  }
  return result;
}

class BacktestResult {
  constructor(runs, priceSeriesUsed) {
    this.runs = runs;
    this.priceSeriesUsed = priceSeriesUsed;
  }

  get numRuns() {
    return this.runs.length;
  }

  values(extractor) {
    return this.runs.map(extractor);
  }

  summary() {
    const endings = this.values((r) => r.effectiveEndingValue);
    const invested = this.values((r) => r.totalCashInvested);
    const returns = this.values((r) => r.totalReturnPct);
    const startPrices = this.values((r) => r.startingPrice);
    const endPrices = this.values((r) => r.endingPrice);

    const years = (this.priceSeriesUsed[0].length - 1) / 12;
    const annualReturns = returns.map((r) => Math.pow(1 + r, 1 / years) - 1);

    let q1, q3;
    if (this.numRuns >= 4) {
      const qs = quantilesInclusive(returns, 4);
      q1 = qs[0];
      q3 = qs[2];
    } else {
      q1 = Math.min(...returns);
      q3 = Math.max(...returns);
    }

    return {
      numRuns: this.numRuns,
      medianReturnPct: median(returns) * 100,
      avgReturnPct: mean(returns) * 100,
      iqrReturnLowPct: q1 * 100,
      iqrReturnHighPct: q3 * 100,
      medianAnnualReturnPct: median(annualReturns) * 100,
      medianCashInvested: median(invested),
      medianEndingPortfolioValue: median(endings),
      startingPrice: startPrices[0],
      medianEndingPrice: median(endPrices),
      medianMaxDrawdownPct: median(this.values((r) => r.maxDrawdownPct)) * 100,
      medianCapitalEfficiencyPct: median(this.values((r) => r.capitalEfficiencyPct)) * 100,
    };
  }

  // Median index price across all runs, for each month index.
  medianPriceByMonth() {
    const numMonths = this.priceSeriesUsed[0].length;
    const out = new Array(numMonths);
    for (let m = 0; m < numMonths; m++) {
      out[m] = median(this.priceSeriesUsed.map((series) => series[m]));
    }
    return out;
  }
}

function runBacktest({ strategy, priceParams, startingSavings, monthlyIncome, numRuns = 50, reusePrices = null }) {
  let priceSeriesList;
  if (reusePrices !== null) {
    priceSeriesList = reusePrices;
  } else {
    priceSeriesList = [];
    for (let i = 0; i < numRuns; i++) {
      priceSeriesList.push(generatePriceSeries(priceParams));
    }
  }

  const results = [];
  for (const prices of priceSeriesList) {
    const strategyCopy = strategy.clone();
    results.push(runSimulation(prices, strategyCopy, startingSavings, monthlyIncome));
  }

  return new BacktestResult(results, priceSeriesList);
}

function generateSharedPriceData(priceParams, numRuns) {
  const list = [];
  for (let i = 0; i < numRuns; i++) {
    list.push(generatePriceSeries(priceParams));
  }
  return list;
}

function compareStrategies({ strategies, priceParams, startingSavings, monthlyIncome, numRuns = 50, sharedPrices = null }) {
  if (sharedPrices === null) {
    sharedPrices = generateSharedPriceData(priceParams, numRuns);
  }

  const rows = [];
  let marketResult = null;

  for (const strategy of strategies) {
    const result = runBacktest({
      strategy,
      priceParams,
      startingSavings,
      monthlyIncome,
      numRuns,
      reusePrices: sharedPrices,
    });
    if (marketResult === null) marketResult = result;
    const s = result.summary();
    rows.push({
      name: strategy.name,
      medianReturnPct: s.medianReturnPct,
      medianAnnualReturnPct: s.medianAnnualReturnPct,
      medianCashInvested: s.medianCashInvested,
      medianEndingPortfolioValue: s.medianEndingPortfolioValue,
      medianMaxDrawdownPct: s.medianMaxDrawdownPct,
      medianCapitalEfficiencyPct: s.medianCapitalEfficiencyPct,
    });
  }

  rows.sort((a, b) => b.medianReturnPct - a.medianReturnPct);
  const bestReturn = rows.length ? rows[0].medianReturnPct : 0.0;
  for (const row of rows) row.returnGapPct = bestReturn - row.medianReturnPct;

  return { rows, marketResult };
}
