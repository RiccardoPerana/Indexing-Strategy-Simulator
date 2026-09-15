/*
 * strategy.js
 *
 * The rule engine. A Strategy is data: a list of Rules, each pairing a
 * Trigger with an Action. All matching rules apply in order, each
 * transforming the running buy amount before the next rule sees it.
 */

const COMPARE_OPS = {
  lte: (a, b) => a <= b,
  lt: (a, b) => a < b,
  gte: (a, b) => a >= b,
  gt: (a, b) => a > b,
};

class Trigger {
  constructor({
    type,
    event = null,
    streak = null,
    operator = null,
    value = null,
    mode = null,
    children = null,
    period = null,
    fastPeriod = null,
    slowPeriod = null,
    direction = null,
    side = null,
  }) {
    this.type = type;
    this.event = event;
    this.streak = streak;
    this.operator = operator;
    this.value = value;
    // Only used by type "logic" -- a compound trigger combining several
    // child Triggers with AND ("all") / OR ("any") / NOT ("not", first
    // child only) semantics, built by the block-editor UI (see
    // block_editor.js). No preset uses one directly, so every other
    // trigger type is unaffected.
    this.mode = mode;
    this.children = children;
    // Only used by the price-indicator trigger types below ("ma_cross",
    // "ma_state", "ma_dual_cross", "ema_cross", "ema_state",
    // "rsi_threshold"). `period` is in MONTHS (this simulator has no
    // daily resolution).
    this.period = period;
    this.fastPeriod = fastPeriod;
    this.slowPeriod = slowPeriod;
    this.direction = direction;
    this.side = side;
  }

  matches(ctx) {
    switch (this.type) {
      case "event":
        return ctx.event === this.event;
      case "sequential_loss":
        return ctx.lossStreak >= (this.streak ?? 1);
      case "sequential_gain":
        return ctx.gainStreak >= (this.streak ?? 1);
      case "return_threshold":
        return COMPARE_OPS[this.operator](ctx.monthlyReturn, this.value);
      case "drawdown_from_peak":
        return ctx.drawdownFromPeak <= this.value;
      case "logic": {
        if (!this.children || this.children.length === 0) return false;
        if (this.mode === "not") return !this.children[0].matches(ctx);
        const results = this.children.map((c) => c.matches(ctx));
        return this.mode === "any" ? results.some(Boolean) : results.every(Boolean);
      }
      // --- price-indicator triggers (see indicators.js) ---
      case "price_threshold":
        return COMPARE_OPS[this.operator](ctx.price, this.value);
      case "ma_cross":
        return crossMatches(Indicators.sma(ctx.prices, this.period), ctx, this.direction);
      case "ma_state":
        return stateMatches(Indicators.sma(ctx.prices, this.period), ctx, this.side);
      case "ema_cross":
        return crossMatches(Indicators.ema(ctx.prices, this.period), ctx, this.direction);
      case "ema_state":
        return stateMatches(Indicators.ema(ctx.prices, this.period), ctx, this.side);
      case "ma_dual_cross":
        return dualCrossMatches(
          Indicators.sma(ctx.prices, this.fastPeriod),
          Indicators.sma(ctx.prices, this.slowPeriod),
          ctx,
          this.direction
        );
      case "rsi_threshold": {
        const v = Indicators.rsi(ctx.prices, this.period)[ctx.monthIndex];
        if (v === null) return false;
        return COMPARE_OPS[this.operator](v, this.value);
      }
      default:
        throw new Error(`Unknown trigger type: ${this.type}`);
    }
  }
}

// price vs. a single indicator series crossing this month
function crossMatches(series, ctx, direction) {
  const i = ctx.monthIndex;
  if (i < 1) return false;
  const cur = series[i], prev = series[i - 1];
  if (cur === null || prev === null) return false;
  const prevPrice = ctx.prices[i - 1], curPrice = ctx.prices[i];
  return direction === "up" ? prevPrice <= prev && curPrice > cur : prevPrice >= prev && curPrice < cur;
}

// price currently above/below a single indicator series
function stateMatches(series, ctx, side) {
  const cur = series[ctx.monthIndex];
  if (cur === null) return false;
  return side === "above" ? ctx.price > cur : ctx.price < cur;
}

// two indicator series (fast vs. slow) crossing this month
function dualCrossMatches(fastSeries, slowSeries, ctx, direction) {
  const i = ctx.monthIndex;
  if (i < 1) return false;
  const fCur = fastSeries[i], fPrev = fastSeries[i - 1];
  const sCur = slowSeries[i], sPrev = slowSeries[i - 1];
  if (fCur === null || fPrev === null || sCur === null || sPrev === null) return false;
  return direction === "up" ? fPrev <= sPrev && fCur > sCur : fPrev >= sPrev && fCur < sCur;
}

class Action {
  constructor({ type, value = null, start = 1.0, increment = 0.0, cap = null }) {
    this.type = type;
    this.value = value;
    this.start = start;
    this.increment = increment;
    this.cap = cap;
  }

  apply(baseBuy, streak = 1) {
    switch (this.type) {
      case "multiply":
        return baseBuy * this.value;
      case "set_fixed":
        return this.value;
      case "add_fixed":
        return baseBuy + this.value;
      case "skip":
        return 0.0;
      case "scale_with_streak": {
        let multiplier = this.start + this.increment * (streak - 1);
        if (this.cap !== null && this.cap !== undefined) {
          multiplier = Math.min(multiplier, this.cap);
        }
        return baseBuy * multiplier;
      }
      default:
        throw new Error(`Unknown action type: ${this.type}`);
    }
  }
}

class Rule {
  constructor(trigger, action) {
    this.trigger = trigger;
    this.action = action;
  }
}

// "Start high, then drop to income level" style base-buy override.
class DepletingBaseBuy {
  constructor(preferredAmount, fallbackAmount) {
    this.preferredAmount = preferredAmount;
    this.fallbackAmount = fallbackAmount;
  }

  compute(availableCash) {
    return availableCash >= this.preferredAmount ? this.preferredAmount : this.fallbackAmount;
  }

  clone() {
    return new DepletingBaseBuy(this.preferredAmount, this.fallbackAmount);
  }
}

class Strategy {
  constructor({ name, rules = [], baseBuyOverride = null, allowSelling = false, description = "" }) {
    this.name = name;
    this.rules = rules;
    this.baseBuyOverride = baseBuyOverride;
    this.allowSelling = allowSelling;
    this.description = description;
  }

  // `ctx` carries everything a Trigger might need to evaluate itself:
  // {event, monthlyReturn, lossStreak, gainStreak, drawdownFromPeak,
  //  availableCash, prices, monthIndex, price} -- see simulator.js, which
  // builds it fresh each month.
  computeBuyAmount(baseBuy, ctx) {
    let amount = baseBuy;
    if (this.baseBuyOverride !== null) {
      amount = this.baseBuyOverride.compute(ctx.availableCash);
    }

    for (const rule of this.rules) {
      if (rule.trigger.matches(ctx)) {
        let relevantStreak = 1;
        if (rule.trigger.type === "sequential_loss") relevantStreak = ctx.lossStreak;
        else if (rule.trigger.type === "sequential_gain") relevantStreak = ctx.gainStreak;
        amount = rule.action.apply(amount, relevantStreak);
      }
    }

    return Math.max(0.0, amount);
  }

  // Each backtest run needs its own deep copy, so a stateful
  // DepletingBaseBuy's patched fallback never leaks across runs.
  clone() {
    return new Strategy({
      name: this.name,
      description: this.description,
      allowSelling: this.allowSelling,
      rules: this.rules.map(
        (r) => new Rule(new Trigger({ ...r.trigger }), new Action({ ...r.action }))
      ),
      baseBuyOverride: this.baseBuyOverride ? this.baseBuyOverride.clone() : null,
    });
  }
}
