/*
 * market_events.js
 *
 * Classifies a month's return into one of six named events. A return
 * landing exactly on a threshold goes to the milder bucket.
 */

const MarketEvent = Object.freeze({
  CRASH: "Crash",
  EXTREME_LOSS: "Extreme Loss",
  LOSS: "Loss",
  GAIN: "Gain",
  EXTREME_GAIN: "Extreme Gain",
  BUBBLE: "Bubble",
});

function classifyEvent(monthlyReturn) {
  if (monthlyReturn < -0.10) return MarketEvent.CRASH;
  if (monthlyReturn < -0.06) return MarketEvent.EXTREME_LOSS;
  if (monthlyReturn < 0) return MarketEvent.LOSS;
  if (monthlyReturn <= 0.06) return MarketEvent.GAIN;
  if (monthlyReturn <= 0.10) return MarketEvent.EXTREME_GAIN;
  return MarketEvent.BUBBLE;
}
