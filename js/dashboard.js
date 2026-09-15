/*
 * dashboard.js
 *
 * Non-chart-rendering dashboard logic: the stats groups shown in the
 * Output panel, and the sustained rally/decline trend detector used to
 * highlight segments of the median price line.
 */

// Backtest stats as grouped {label, value, raw} rows. `raw` is the
// signed numeric value for rows
// where sign has real meaning (for coloring); null otherwise. For the
// IQR row, `raw` is [low, high].
function summaryGroups(result) {
  const s = result.summary();
  const eur = (n) => `€${Math.round(n).toLocaleString("en-US")}`;
  return [
    [
      "Return",
      [
        ["Median return", `${s.medianReturnPct.toFixed(2)}%`, s.medianReturnPct],
        ["Median annualized return", `${s.medianAnnualReturnPct.toFixed(2)}%`, s.medianAnnualReturnPct],
        [
          "Typical range (IQR)",
          `${s.iqrReturnLowPct.toFixed(1)}% to ${s.iqrReturnHighPct.toFixed(1)}%`,
          [s.iqrReturnLowPct, s.iqrReturnHighPct],
        ],
      ],
    ],
    [
      "Portfolio",
      [
        ["Median cash invested", eur(s.medianCashInvested), null],
        ["Median ending value", eur(s.medianEndingPortfolioValue), null],
      ],
    ],
    [
      "Price",
      [
        ["Starting price", `€${s.startingPrice.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, null],
        ["Median ending price", `€${s.medianEndingPrice.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, null],
      ],
    ],
  ];
}

/**
 * Identify sustained rallies/declines in `prices` (expected to be the
 * MEDIAN-of-many-runs series, not a single raw path -- median-of-many-
 * runs is a cross-sectional statistic, not a real trajectory, and is
 * meaningfully smoother than any individual run since each run's sharp
 * moves happen at different times and get averaged out; the thresholds
 * below are calibrated against that smoother series). A zigzag/
 * peak-trough pass finds swing points; each resulting segment must ALSO
 * clear an annualized-rate bar and stay under `maxSegmentYears` to be
 * reported, so gentle drift and multi-decade spans are excluded.
 *
 * Returns { declineSegments, rallySegments }, each a list of
 * [startIndex, endIndex] pairs (month indices into `prices`).
 */
function findSustainedTrends(
  prices,
  {
    reversalThreshold = 0.10,
    rallyAnnualRate = 0.05,
    declineAnnualRate = -0.04,
    maxSegmentYears = 5.0,
  } = {}
) {
  const n = prices.length;
  if (n < 2) return { declineSegments: [], rallySegments: [] };

  const maxSegmentMonths = maxSegmentYears * 12;

  function annualizedRate(i0, i1) {
    const years = (i1 - i0) / 12;
    if (years <= 0 || prices[i0] <= 0) return 0.0;
    return Math.pow(prices[i1] / prices[i0], 1 / years) - 1;
  }

  const declineSegments = [];
  const rallySegments = [];
  let pivotIdx = 0;
  let maxIdx = 0, maxPrice = prices[0];
  let minIdx = 0, minPrice = prices[0];
  let trend = null; // null, "up", or "down"

  for (let i = 1; i < n; i++) {
    const price = prices[i];
    if (price > maxPrice) { maxPrice = price; maxIdx = i; }
    if (price < minPrice) { minPrice = price; minIdx = i; }

    if (trend !== "down" && maxPrice > 0 && (price - maxPrice) / maxPrice <= -reversalThreshold) {
      if (trend === "up" && annualizedRate(pivotIdx, maxIdx) >= rallyAnnualRate && maxIdx - pivotIdx <= maxSegmentMonths) {
        rallySegments.push([pivotIdx, maxIdx]);
      }
      pivotIdx = maxIdx;
      trend = "down";
      minIdx = i; minPrice = price;
      continue;
    }

    if (trend !== "up" && minPrice > 0 && (price - minPrice) / minPrice >= reversalThreshold) {
      if (trend === "down" && annualizedRate(pivotIdx, minIdx) <= declineAnnualRate && minIdx - pivotIdx <= maxSegmentMonths) {
        declineSegments.push([pivotIdx, minIdx]);
      }
      pivotIdx = minIdx;
      trend = "up";
      maxIdx = i; maxPrice = price;
      continue;
    }
  }

  // close out whatever trend is still running at the end of the series
  if (trend === "up" && maxIdx > pivotIdx && annualizedRate(pivotIdx, maxIdx) >= rallyAnnualRate && maxIdx - pivotIdx <= maxSegmentMonths) {
    rallySegments.push([pivotIdx, maxIdx]);
  } else if (trend === "down" && minIdx > pivotIdx && annualizedRate(pivotIdx, minIdx) <= declineAnnualRate && minIdx - pivotIdx <= maxSegmentMonths) {
    declineSegments.push([pivotIdx, minIdx]);
  }

  return { declineSegments, rallySegments };
}
