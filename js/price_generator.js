/*
 * price_generator.js
 *
 * Generates synthetic monthly index price histories using Geometric
 * Brownian Motion + jump diffusion, with each run sampling its own
 * drift/volatility regime and compensating for the crash/bubble jump
 * bias (see generatePriceSeries below).
 *
 * There is no seed support -- every run is genuinely random -- so this
 * uses Math.random() and a Box-Muller transform for the normal draws.
 */

const PriceGeneratorDefaults = Object.freeze({
  startPrice: 100.0,
  years: 50,

  driftMean: 0.03,
  driftStd: 0.045,
  volMin: 0.08,
  volMax: 0.10,

  crashIntensity: 0.017,
  crashJumpMean: -0.20,
  crashJumpStd: 0.08,

  bubbleIntensity: 0.012,
  bubbleJumpMean: 0.15,
  bubbleJumpStd: 0.07,
});

// Box-Muller transform -- standard normal, then scaled/shifted.
function gaussianRandom(mean = 0, std = 1) {
  let u1 = 0;
  while (u1 === 0) u1 = Math.random(); // avoid log(0)
  const u2 = Math.random();
  const z0 = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  return mean + std * z0;
}

function uniformRandom(a, b) {
  return a + Math.random() * (b - a);
}

/**
 * Generate one monthly price history using jump-diffusion.
 * Returns an array of `years*12 + 1` prices (index 0 is the start price).
 */
function generatePriceSeries(params) {
  const p = Object.assign({}, PriceGeneratorDefaults, params);
  const months = p.years * 12;

  const annualDrift = gaussianRandom(p.driftMean, p.driftStd);
  const annualVol = uniformRandom(p.volMin, p.volMax);

  const jumpBiasPerYear = p.crashIntensity * p.crashJumpMean + p.bubbleIntensity * p.bubbleJumpMean;
  const compensatedAnnualDrift = annualDrift - jumpBiasPerYear;

  const monthlyDrift = compensatedAnnualDrift / 12;
  const monthlyVol = annualVol / Math.sqrt(12);

  const crashProbPerMonth = p.crashIntensity / 12;
  const bubbleProbPerMonth = p.bubbleIntensity / 12;

  const prices = [p.startPrice];
  let price = p.startPrice;

  for (let m = 0; m < months; m++) {
    let logReturn = gaussianRandom(monthlyDrift, monthlyVol);

    if (Math.random() < crashProbPerMonth) {
      logReturn += gaussianRandom(p.crashJumpMean, p.crashJumpStd);
    }
    if (Math.random() < bubbleProbPerMonth) {
      logReturn += gaussianRandom(p.bubbleJumpMean, p.bubbleJumpStd);
    }

    price = price * Math.exp(logReturn);
    prices.push(price);
  }

  return prices;
}
