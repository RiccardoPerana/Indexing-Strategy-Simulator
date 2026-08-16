# Indexing Strategy Simulator

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

<img width="1920" height="1080" alt="Main Window" src="https://github.com/user-attachments/assets/2e96b179-488d-4d14-8e52-9ad2c5e5a9f3" />

A backtesting tool for DCA-style (dollar-cost-averaging) index investing
strategies. Define a strategy as a set of simple rules ("buy more during
a crash," "escalate contributions the longer a downturn runs"), test it
against dozens of randomly generated 50-year price histories, and see
how it stacks up — either against its own past runs, or against every
other strategy at once.

Ships as both a desktop GUI and a console app, sharing the exact same
underlying simulation engine.

**A note on the data:** this deliberately does **not** backtest against
historical market data. Prices are randomly generated (see
[How prices are generated](#how-prices-are-generated)) so that a
strategy's score reflects how it behaves across a genuine range of
possible markets, not how well it happened to fit one specific history —
testing "20% down, buy double" against the last 50 years of the S&P 500
would make it look great, precisely because that's the exact history
being fit to, not because the rule is actually sound. See
[Known scope decisions](#known-scope-decisions) for the full reasoning.

## Features

- **Rule-based strategy engine** — every strategy is data (a list of
  trigger → action rules), not custom code. 12 ready-made strategies
  covering common approaches (dollar-cost averaging, crash buying,
  momentum, drawdown-based accumulation, and more), plus a visual
  strategy builder for your own.
- **Realistic price simulation** — Geometric Brownian Motion with jump
  diffusion, not a single fixed growth assumption. Each backtest run
  samples its own market regime, so results reflect a genuine range of
  possible futures rather than one hardcoded scenario.
- **Median-first statistics** — return, annualized return, and ending
  portfolio value are reported as medians, not averages, since average
  outcomes for a compounding process are structurally skewed upward by
  rare extreme runs (see [Why median, not average](#why-median-not-average)).
- **Compare All** — run every strategy against identical market data in
  one click and see them ranked side by side, with return, annualized
  return, ending value, maximum drawdown, and gap-to-best-performer for
  each.
- **Interactive chart** — click-drag to pan, scroll to zoom, toggle
  between linear and logarithmic price scales, and automatic highlighting
  of sustained multi-year rallies and declines.
- **Save custom strategies** for the current session, so you can build
  several variations and compare them without re-entering rules each
  time.

## Screenshots

### Compare All
<img width="1920" height="1080" alt="Compare All" src="https://github.com/user-attachments/assets/9caa7c22-6432-4d0e-a7c1-ed87e48a6bf2" />


### Custom Strategy Builder
<img width="573" height="870" alt="Custom Strategy Builder" src="https://github.com/user-attachments/assets/207b5e65-0d5b-4873-b958-a2928a5abd0f" />


### Linear vs. logarithmic scale
<img width="1728" height="1080" alt="scale-comparison" src="https://github.com/user-attachments/assets/5785b5f7-3a93-4893-aef8-9da0640538a8" />


## Installation

### Run from source

Requires Python 3.9+.

```bash
pip install -r requirements.txt
python gui_tk.py      # desktop GUI
python main.py        # console version
```

### Standalone Windows executable

The easiest option: **[download the latest build from Releases](../../releases/latest)**
— no Python installation needed at all.

To build one yourself instead:

```bash
build_exe.bat
```

This runs on Windows only (see [Building a standalone executable](#building-a-standalone-executable)
below for details and why).

## Usage

### Desktop GUI

Settings on the left, chart in the middle, results on the right.

1. Set the market parameters (starting price, years, number of
   simulation runs) and your investing parameters (starting capital,
   monthly contribution).
2. Pick a strategy from the dropdown, or choose **Custom...** to build
   your own from triggers and actions.
3. **Run Backtest** to simulate your current settings, or **Quick Run**
   to run preset #1 with all defaults instantly.
4. **Compare All** runs every strategy — presets plus any custom
   strategies you've built this session — against identical price data
   and ranks them in a table. Toggle between the table and the
   underlying market chart with the button that appears at the bottom
   of the settings panel.
5. Toggle the chart between linear and logarithmic price scale with the
   button at the very bottom of the settings panel.

### Console

<img width="747" height="892" alt="Console" src="https://github.com/user-attachments/assets/ac865c8a-0155-479a-adf2-4e318aef1c2a" />

```bash
python main.py
```

Walks you through the same settings via a text menu, then opens a
combined chart + stats window. Useful for quick scripting-style runs or
environments without a GUI.

## Why median, not average

For any compounding growth process:

```
mean(outcome) = median(outcome) × e^(½ · variance · time)
```

This is a direct consequence of Jensen's inequality (the exponential
function is convex) — that correction term is never negative, so
**average return sits above median return structurally**, not as a
quirk of any one run, and increasingly so over longer horizons and
higher volatility. Losses are also capped at −100% while gains are
unbounded, which pushes the same direction independently.

Median describes what a single investor living through *one* actual
timeline should expect. Average describes a hypothetical pool of many
parallel timelines averaged together — which nobody actually
experiences. This project reports median as the headline number
throughout, with average kept as a secondary skew signal.

One subtlety: this logic can point the *opposite* direction once
annualized — a handful of near-total-loss runs annualize toward −100%,
which can pull *average annual* return *below* median (the reverse of
what happens with total, non-annualized return). Neither direction is
assumed; each statistic is computed and reported on its own terms.

## How prices are generated

Prices use **Geometric Brownian Motion + Jump Diffusion** — a standard
upgrade over plain GBM that adds realistic sudden drops and spikes on
top of everyday diffusion noise:

- **Diffusion** — month-to-month variation drawn from a normal
  distribution.
- **Jumps** — two independent rare-event processes: occasional sharp
  **crash** jumps (large, negative) and occasional sharp **bubble**
  jumps (large, positive), asymmetric in both frequency and size (crashes
  more common and larger, a realistic stylized fact).

No run uses one fixed expected return. Each simulation run samples its
own annual drift and volatility once, at the start of that run, from
ranges defined in `price_generator.py` — so a backtest's results reflect
a genuine distribution of possible market conditions, not a single
scripted outcome. The jump asymmetry is compensated for automatically,
so a run sampled at "drift = 0%" actually averages to 0%, not to a
value silently dragged down by the crash/bubble imbalance.

## How the strategy engine works

Every strategy is data: a list of **rules**, where each rule is a
**trigger** (when does this fire?) paired with an **action** (what
happens to the buy amount?).

```python
Rule(
    trigger=Trigger(type="event", event=MarketEvent.CRASH),
    action=Action(type="set_fixed", value=float("inf")),  # buy as much as possible
)
```

All matching rules apply, in order, each transforming the running buy
amount before the next rule sees it — so a per-event multiplier and a
streak-escalation rule compose naturally rather than competing (a 1.5x
loss multiplier combined with a +1x/month streak escalation, on a
3-month streak, buys 1.5 × 3 = 4.5x the base amount). If nothing
matches, the base buy (monthly contribution, unless overridden) is used
unchanged.

**Trigger types:**
- `"event"` — fires on a specific `MarketEvent` (Crash, Extreme Loss,
  Loss, Gain, Extreme Gain, Bubble)
- `"sequential_loss"` / `"sequential_gain"` — fires after N consecutive
  losing/gaining months
- `"return_threshold"` — fires when the return crosses a custom number,
  for thresholds that don't line up with the six named events
- `"drawdown_from_peak"` — fires when price is a given fraction below
  the highest price reached so far in the simulation

**Action types:**
- `"multiply"` — scale the base buy (2.0 = double, 0.5 = half)
- `"set_fixed"` — buy exactly this amount (`float('inf')` = as much as
  available cash allows)
- `"add_fixed"` — add a flat amount to the base buy
- `"skip"` — buy nothing this month
- `"scale_with_streak"` — escalate a multiplier the longer a streak
  runs, up to a cap

### Adding a new strategy

No changes to the simulation engine needed — add a factory function to
`presets.py` that returns a `Strategy` built from rules, and register it
in `ALL_PRESETS`.

## Project structure

| File | Responsibility |
|---|---|
| `market_events.py` | Classifies a month's return into one of six named events (Crash / Extreme Loss / Loss / Gain / Extreme Gain / Bubble) |
| `price_generator.py` | Generates random monthly price histories (GBM + jump diffusion) |
| `strategy.py` | The rule engine: `Trigger` + `Action` + `Rule` + `Strategy` |
| `presets.py` | Built-in example strategies, built entirely from the rule engine |
| `simulator.py` | Runs one strategy against one price history, month by month |
| `backtest.py` | Runs N simulations, aggregates stats, and powers Compare All |
| `saved_strategies.py` | Session-only persistence for custom strategies built via the GUI |
| `dashboard.py` | Chart-drawing and stats formatting, shared by both front ends |
| `interactive_chart.py` | Click-drag pan / scroll-wheel zoom for the chart |
| `gui_theme.py` | Color palette and ttkbootstrap theme registration for the GUI |
| `gui_tk.py` | The desktop GUI (Tkinter + ttk, themed with ttkbootstrap) |
| `cli.py` | The console front end |
| `main.py` | Console entry point (`python main.py`) |
| `bank_simulator.py` | A standalone fixed-deposit savings calculator, used by the console version |

## Building a standalone executable

`build_exe.bat` uses [PyInstaller](https://pyinstaller.org/) to bundle
the GUI and all its dependencies into a single `IndexingStrategySimulator.exe`
that runs on any Windows machine with no Python installation required.

This has to be run **on Windows** — PyInstaller builds an executable for
whatever operating system it runs on; it can't cross-compile a Windows
`.exe` from Linux or macOS. If you're distributing to Mac or Linux users,
run the same script (renamed `build_exe.sh` with the equivalent
`pyinstaller` command) on that platform instead.

## Known scope decisions

- **Selling is not implemented.** The project is scoped around wealth
  *accumulation* strategies specifically, not trade timing in the buy/
  sell sense — and a meaningful part of what a moving-average-triggered
  approach would add is already covered by the drawdown-from-peak and
  streak-based triggers already in the rule engine (buying more after
  sustained declines or gains). A literal sell action would be a bigger
  scope expansion than a genuinely new analytical capability.
  `Strategy.allow_selling` remains reserved if that changes.
- **No fees or expense ratios.** Real index funds have costs, and over a
  50-year horizon they compound into a real effect worth modeling
  eventually. Left out of this version deliberately: the settings screen
  already asks for several numbers, and every additional parameter is a
  small tax on how approachable the tool feels. A reasonable next
  addition, just not before the core mechanics were solid.
- **No historical backtesting — prices are synthetic by design, not by
  omission.** Sourcing clean, correctly-licensed historical price data
  is a substantial project in its own right. More importantly: testing a
  strategy against one specific real history (e.g. the S&P 500's last 50
  years) invites exactly the "past performance is not indicative of
  future results" trap — a strategy tuned to look good on one historical
  sequence isn't demonstrably *good*, it's demonstrably *fit to that
  sequence*. The one assumption this project does lean on — that
  equities carry a positive long-run return expectation, generally above
  bonds — is well-established enough to bake into the price model's
  drift calibration. Everything else (the specific path, when crashes
  land, volatility clustering) is left random on purpose, so a strategy
  has to hold up across a genuine distribution of possible markets
  rather than one historical anecdote.
- **Gain/Loss boundary:** treated as continuous, with Gain/Loss extending
  up to the 6% mark where Extreme Gain/Loss begins — see
  `market_events.py` if you'd rather define the boundary differently.
- **Saved custom strategies are session-only**, deleted when the GUI
  closes, by design — simpler than building a strategy management/delete
  UI for a feature capped at 10 entries.

## License

[MIT](LICENSE) — see the `LICENSE` file. Update the copyright holder name
in that file before publishing if you'd like your name on it specifically
rather than the generic placeholder.
