/*
 * indicators.js
 *
 * Price-derived technical indicators (SMA, EMA, RSI) for the block
 * editor's moving-average/RSI condition blocks (see block_editor.js and
 * the "ma_cross"/"ma_state"/"ma_dual_cross"/"ema_cross"/"ema_state"/
 * "rsi_threshold" trigger types in strategy.js).
 *
 * Each function returns a full array (index-aligned with the `prices`
 * array it was given, i.e. one point per MONTH -- this simulator has no
 * daily resolution, so "period" here means months, not trading days like
 * a typical charting tool). SMA and RSI are `null` until there is enough
 * history to compute them; EMA is seeded with the first price, so it has
 * a value from month 0.
 *
 * Results are cached per (prices array identity, indicator, period) via a
 * WeakMap keyed on the prices array itself. A price array never changes
 * once generated, so a cached series is valid for as long as the array
 * lives (including when "Reuse previous run's data" runs it again), and a
 * Trigger can ask for "its" series every month without redoing the
 * O(months) work each time.
 */

const Indicators = (function () {
  "use strict";

  const cacheByPrices = new WeakMap();

  function seriesCache(prices) {
    let m = cacheByPrices.get(prices);
    if (!m) {
      m = new Map();
      cacheByPrices.set(prices, m);
    }
    return m;
  }

  function sma(prices, period) {
    const cache = seriesCache(prices);
    const key = `sma:${period}`;
    if (cache.has(key)) return cache.get(key);

    const out = new Array(prices.length).fill(null);
    let sum = 0;
    for (let i = 0; i < prices.length; i++) {
      sum += prices[i];
      if (i >= period) sum -= prices[i - period];
      if (i >= period - 1) out[i] = sum / period;
    }
    cache.set(key, out);
    return out;
  }

  function ema(prices, period) {
    const cache = seriesCache(prices);
    const key = `ema:${period}`;
    if (cache.has(key)) return cache.get(key);

    const out = new Array(prices.length).fill(null);
    const alpha = 2 / (period + 1);
    let prev = prices[0];
    out[0] = prev;
    for (let i = 1; i < prices.length; i++) {
      prev = alpha * prices[i] + (1 - alpha) * prev;
      out[i] = prev;
    }
    cache.set(key, out);
    return out;
  }

  function rsiFromAverages(avgGain, avgLoss) {
    if (avgLoss === 0) return avgGain === 0 ? 50 : 100;
    const rs = avgGain / avgLoss;
    return 100 - 100 / (1 + rs);
  }

  // Standard Wilder's RSI: seed with a simple average of the first
  // `period` gains/losses, then smooth every month after that.
  function rsi(prices, period) {
    const cache = seriesCache(prices);
    const key = `rsi:${period}`;
    if (cache.has(key)) return cache.get(key);

    const out = new Array(prices.length).fill(null);
    let avgGain = 0;
    let avgLoss = 0;
    for (let i = 1; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      const gain = Math.max(change, 0);
      const loss = Math.max(-change, 0);

      if (i < period) {
        avgGain += gain;
        avgLoss += loss;
      } else if (i === period) {
        avgGain = (avgGain + gain) / period;
        avgLoss = (avgLoss + loss) / period;
        out[i] = rsiFromAverages(avgGain, avgLoss);
      } else {
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
        out[i] = rsiFromAverages(avgGain, avgLoss);
      }
    }
    cache.set(key, out);
    return out;
  }

  return { sma, ema, rsi };
})();
