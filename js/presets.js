/*
 * presets.js
 *
 * Ready-made strategies covering common accumulation approaches: dollar-
 * cost averaging, crash buying, momentum, drawdown-based accumulation,
 * and others. Each is built entirely from Strategy/Rule/Trigger/Action --
 * no custom code paths per strategy.
 */

function buyMaxEveryMonth() {
  return new Strategy({
    name: "Full Capital Deployment",
    description:
      "Invests all available capital every month, in both rising and falling markets, " +
      "with no attempt at market timing. The most aggressive strategy in this set.",
    rules: Object.values(MarketEvent).map(
      (e) => new Rule(new Trigger({ type: "event", event: e }), new Action({ type: "set_fixed", value: Infinity }))
    ),
  });
}

function startHighThenIncome() {
  return new Strategy({
    name: "Front-Loaded Contribution",
    description:
      "Contributes €500 per month for as long as available savings permit, then reduces to the " +
      "standard monthly contribution level thereafter. This switch is driven by available savings, " +
      "not market performance.",
    baseBuyOverride: new DepletingBaseBuy(500.0, 0.0),
  });
}

function multiplyOnSequentialLosses(multiplier = 2.0, streak = 2) {
  return new Strategy({
    name: "Sequential Loss Amplification",
    description:
      `Increases the monthly contribution by a factor of ${multiplier}x once the market has declined ` +
      `for ${streak} consecutive months. The standard contribution applies at all other times, and ` +
      `resumes as soon as the losing streak ends.`,
    rules: [new Rule(new Trigger({ type: "sequential_loss", streak }), new Action({ type: "multiply", value: multiplier }))],
  });
}

function decreaseOnSequentialGains(multiplier = 0.5, streak = 2) {
  return new Strategy({
    name: "Sequential Gain Moderation",
    description:
      `Reduces the monthly contribution to a factor of ${multiplier}x once the market has advanced ` +
      `for ${streak} consecutive months. The standard contribution applies at all other times, and ` +
      `resumes as soon as the winning streak ends.`,
    rules: [new Rule(new Trigger({ type: "sequential_gain", streak }), new Action({ type: "multiply", value: multiplier }))],
  });
}

function maxBuyOnCrash() {
  return new Strategy({
    name: "Crash-Triggered Maximum Allocation",
    description:
      "Allocates the maximum available capital during a Crash month (a decline exceeding 10%); the " +
      "standard contribution applies in all other months.",
    rules: [new Rule(new Trigger({ type: "event", event: MarketEvent.CRASH }), new Action({ type: "set_fixed", value: Infinity }))],
  });
}

function maxBuyOnAnyLoss() {
  return new Strategy({
    name: "Broad Downturn Accumulation",
    description:
      "Allocates the maximum available capital during any month of decline — Loss, Extreme Loss, or " +
      "Crash. The standard contribution applies during months of market gains.",
    rules: [
      new Rule(new Trigger({ type: "event", event: MarketEvent.CRASH }), new Action({ type: "set_fixed", value: Infinity })),
      new Rule(new Trigger({ type: "event", event: MarketEvent.EXTREME_LOSS }), new Action({ type: "set_fixed", value: Infinity })),
      new Rule(new Trigger({ type: "event", event: MarketEvent.LOSS }), new Action({ type: "set_fixed", value: Infinity })),
    ],
  });
}

function doubleOnLossOver5pct() {
  return new Strategy({
    name: "Threshold-Based Loss Response",
    description:
      "Doubles the monthly contribution whenever the market has declined by more than 5% over the " +
      "preceding month — a lower threshold than a full Crash designation. The standard contribution " +
      "applies in all other months.",
    rules: [new Rule(new Trigger({ type: "return_threshold", operator: "lte", value: -0.05 }), new Action({ type: "multiply", value: 2.0 }))],
  });
}

function halfOnGainOver10pct() {
  return new Strategy({
    name: "Overextension Moderation",
    description:
      "Reduces the monthly contribution by half following a Bubble month (a gain exceeding 10%). The " +
      "standard contribution applies in all other months.",
    rules: [new Rule(new Trigger({ type: "event", event: MarketEvent.BUBBLE }), new Action({ type: "multiply", value: 0.5 }))],
  });
}

function momentumChasing(multiplier = 1.5, streak = 2) {
  return new Strategy({
    name: "Momentum Chasing",
    description:
      `Increases the monthly contribution by a factor of ${multiplier}x once the market has advanced ` +
      `for ${streak} consecutive months, treating sustained strength as a signal to increase exposure ` +
      `rather than moderate it. The standard contribution applies at all other times, and resumes as ` +
      `soon as the winning streak ends.`,
    rules: [new Rule(new Trigger({ type: "sequential_gain", streak }), new Action({ type: "multiply", value: multiplier }))],
  });
}

function drawdownBuying(multiplier = 2.0, drawdownThreshold = -0.20) {
  const pct = (Math.abs(drawdownThreshold) * 100).toFixed(0);
  return new Strategy({
    name: "Drawdown Accumulation",
    description:
      `Increases the monthly contribution by a factor of ${multiplier}x whenever the index is trading ` +
      `at least ${pct}% below the highest price reached so far in the simulation. The standard ` +
      `contribution applies once the index recovers to within ${pct}% of that high.`,
    rules: [new Rule(new Trigger({ type: "drawdown_from_peak", value: drawdownThreshold }), new Action({ type: "multiply", value: multiplier }))],
  });
}

function dollarCostAverage() {
  return new Strategy({
    name: "Standard Dollar-Cost Averaging",
    description:
      "Contributes a fixed amount each month regardless of market conditions. Serves as the baseline " +
      "against which all other strategies in this set are evaluated.",
    rules: [],
  });
}

function escalateOnLossStreak(increment = 1.0, cap = 5.0) {
  return new Strategy({
    name: "Progressive Downturn Accumulation",
    description:
      `Begins at the standard contribution level and increases it by ${increment}x for every additional ` +
      `consecutive losing month, up to a maximum of ${cap}x. The multiplier resets to the standard level ` +
      `as soon as a gaining month breaks the losing streak.`,
    rules: [
      new Rule(
        new Trigger({ type: "sequential_loss", streak: 1 }),
        new Action({ type: "scale_with_streak", start: 1.0, increment, cap })
      ),
    ],
  });
}

function trendGuardedDeployment(period = 120) {
  const years = period / 12;
  return new Strategy({
    name: "Trend-Guarded Deployment",
    description:
      `Invests all available capital every month, like Full Capital Deployment, except while the index ` +
      `trades below its ${years}-year moving average: then it buys nothing and lets cash build up, and ` +
      `deploys that cash in full as soon as the index climbs back above the average. It gives up a small ` +
      `amount of typical return in exchange for a much better outcome in markets stuck in a long decline.`,
    rules: [
      // Rule order matters: the skip rule runs last so it overrides the
      // all-in rules on any month the index is below its long-run average.
      ...Object.values(MarketEvent).map(
        (e) => new Rule(new Trigger({ type: "event", event: e }), new Action({ type: "set_fixed", value: Infinity }))
      ),
      new Rule(new Trigger({ type: "ma_state", period, side: "below" }), new Action({ type: "skip" })),
    ],
  });
}

// Zero-argument factories, in dropdown order. The first is what Quick Run
// uses. Each call returns a fresh Strategy; its name comes from the
// Strategy itself, so it is written in exactly one place.
const PRESETS = [
  buyMaxEveryMonth,
  startHighThenIncome,
  multiplyOnSequentialLosses,
  decreaseOnSequentialGains,
  maxBuyOnCrash,
  maxBuyOnAnyLoss,
  doubleOnLossOver5pct,
  halfOnGainOver10pct,
  dollarCostAverage,
  escalateOnLossStreak,
  momentumChasing,
  drawdownBuying,
  trendGuardedDeployment,
];

const PRESET_NAMES = PRESETS.map((factory) => factory().name);
