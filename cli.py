"""
cli.py

The interactive command-line menu: collects simulation parameters, lets
the user pick a preset strategy or build a custom one, runs the backtest,
shows the dashboard, and loops back to the start menu -- as described in
the project brief.

NAVIGATION: at any prompt that asks for a value, typing 'b' goes back one
step and 'm' jumps straight to the main menu -- available everywhere, not
just at menu screens. Letters are used (not numbers) specifically so every
number stays free for actual multipliers/amounts, including 0 and negative
values.
"""

from typing import List, Optional, Tuple, Callable, Any

from price_generator import PriceGeneratorParams
from strategy import Strategy, Rule, Trigger, Action
from market_events import MarketEvent
from backtest import run_backtest
from bank_simulator import run_bank_simulation
from dashboard import show_dashboard, print_bank_summary
import presets


class _GoBack(Exception):
    """Raised when the user types 'b' at a prompt."""
    pass


class _GoHome(Exception):
    """Raised when the user types 'm' at a prompt."""
    pass


NAV_HINT = "(b=back, m=main menu)"


def _check_nav(raw: str) -> None:
    """Raise _GoBack/_GoHome if `raw` is a nav command; otherwise no-op."""
    low = raw.strip().lower()
    if low == "b":
        raise _GoBack()
    if low == "m":
        raise _GoHome()


def _ask_float(prompt: str, default: float) -> float:
    while True:
        raw = input(f"{prompt} [{default}] {NAV_HINT}: ").strip()
        _check_nav(raw)
        if raw == "":
            return default
        try:
            return float(raw)
        except ValueError:
            print("  Not a number, try again.")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}] {NAV_HINT}: ").strip()
        _check_nav(raw)
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            print("  Not a number, try again.")


def _ask_optional_float(prompt: str) -> Optional[float]:
    """Like _ask_float, but blank means 'not set' (returns None) rather than a default."""
    while True:
        raw = input(f"{prompt} {NAV_HINT}: ").strip()
        _check_nav(raw)
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print("  Not a number, try again.")


def _run_step_wizard(steps: List[Tuple[str, Callable[[], Any]]]) -> dict:
    """
    Runs a list of (key, ask_fn) steps in order, collecting results into a
    dict keyed by `key`. Each ask_fn takes no arguments and either returns
    a value or raises _GoBack/_GoHome.

    - _GoBack moves to the PREVIOUS step in this same wizard and re-asks
      it (the step's previously collected answer is simply overwritten).
    - _GoBack raised on the very FIRST step re-raises outward, so the
      caller (an outer wizard, or main_menu) can treat "back" from the
      top of a flow as "leave this flow entirely".
    - _GoHome always propagates all the way out to main_menu.
    """
    results: dict = {}
    idx = 0
    while idx < len(steps):
        key, ask_fn = steps[idx]
        try:
            results[key] = ask_fn()
            idx += 1
        except _GoBack:
            if idx == 0:
                raise
            idx -= 1
    return results


def _choose_strategy() -> Strategy:
    print(f"\n-- Choose a Strategy --  {NAV_HINT}")
    for key, (name, _factory) in presets.ALL_PRESETS.items():
        print(f"  {key}. {name}")
    custom_key = str(len(presets.ALL_PRESETS) + 1)
    print(f"  {custom_key}. Build a custom strategy")

    choice = input("Selection: ").strip()
    _check_nav(choice)
    if choice in presets.ALL_PRESETS:
        _, factory = presets.ALL_PRESETS[choice]
        return factory()
    return _build_custom_strategy()


def _make_event_multiplier_step(event: MarketEvent) -> Callable[[], Optional[float]]:
    def ask() -> Optional[float]:
        raw = input(f"Multiplier for '{event.value}' (blank=unaffected) {NAV_HINT}: ").strip()
        _check_nav(raw)
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print("  Not a number, try again.")
            return ask()
    return ask


def _ask_escalation(label: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Asks for a streak-escalation increment, and ONLY follows up with a cap
    question if the user actually wants escalation (non-blank increment).
    Returns (increment, cap), either or both None if skipped.
    """
    increment = _ask_optional_float(
        f"Escalate buy per extra {label} month? (1=2x,3x,4x... blank=skip)")
    if increment is None:
        return None, None
    cap = _ask_optional_float("  Cap the multiplier at (blank=no cap)")
    return increment, cap


def _build_custom_strategy() -> Strategy:
    print("\n-- Custom Strategy Builder --")
    print("Set a multiplier for each market event you want to react to.")
    print("(1 = no change, 2 = double, 0.5 = half, 0 = skip buying)\n")

    events = list(MarketEvent)
    steps: List[Tuple[str, Callable[[], Any]]] = [
        (f"event:{e.value}", _make_event_multiplier_step(e)) for e in events
    ]
    steps.append(("loss_escalation", lambda: _ask_escalation("losing")))
    steps.append(("gain_escalation", lambda: _ask_escalation("gaining")))
    steps.append(("name", lambda: _ask_strategy_name()))

    results = _run_step_wizard(steps)

    rules: List[Rule] = []
    for e in events:
        v = results.get(f"event:{e.value}")
        if v is not None:
            rules.append(Rule(Trigger(type="event", event=e), Action(type="multiply", value=v)))

    loss_increment, loss_cap = results.get("loss_escalation", (None, None))
    if loss_increment is not None:
        rules.append(Rule(
            Trigger(type="sequential_loss", streak=1),
            Action(type="scale_with_streak", start=1.0, increment=loss_increment, cap=loss_cap),
        ))
    gain_increment, gain_cap = results.get("gain_escalation", (None, None))
    if gain_increment is not None:
        rules.append(Rule(
            Trigger(type="sequential_gain", streak=1),
            Action(type="scale_with_streak", start=1.0, increment=gain_increment, cap=gain_cap),
        ))

    name = results.get("name") or "Custom Strategy"
    return Strategy(name=name, rules=rules)


def _ask_strategy_name() -> str:
    raw = input(f"Name this strategy: {NAV_HINT}: ").strip()
    _check_nav(raw)
    return raw


def _choose_data_source(previous_prices: Optional[List[List[float]]]) -> Tuple[str, Optional[List[List[float]]]]:
    if previous_prices is None:
        return "new", None
    print(f"\n-- Data Source --  {NAV_HINT}")
    print("  1. Generate new random price histories")
    print("  2. Reuse the price histories from the previous run")
    choice = input("Selection [1]: ").strip()
    _check_nav(choice)
    if choice == "2":
        return "reused", previous_prices
    return "new", None


def run_investing_simulation_flow(previous_prices: Optional[List[List[float]]]) -> List[List[float]]:
    """Runs one full pass of: configure -> backtest -> dashboard. Returns the price data used, for reuse next time."""
    print("\n-- Price Generator Parameters --")
    print("(Expected return and volatility are intentionally NOT set here --")
    print(" each run randomly samples its own market regime, so the backtest")
    print(" stress-tests the strategy across many different possible futures")
    print(" instead of grading it against one assumed outcome.)")

    step_defs: List[Tuple[str, Callable[[], Any]]] = [
        ("start_price", lambda: _ask_float("Starting index price (€)", 100.0)),
        ("years", lambda: _ask_int("Years per run", 50)),
        ("starting_savings", lambda: _ask_float("Starting savings amount (€)", 10_000.0)),
        ("monthly_income", lambda: _ask_float("Monthly income available to invest (€)", 300.0)),
        ("num_runs", lambda: _ask_int("Number of backtest runs", 50)),
        ("strategy", lambda: _choose_strategy()),
    ]
    if previous_prices is not None:
        step_defs.append(("data_source", lambda: _choose_data_source(previous_prices)))

    results = _run_step_wizard(step_defs)

    price_params = PriceGeneratorParams(start_price=results["start_price"], years=results["years"])
    strategy = results["strategy"]
    if "data_source" in results:
        source_label, reuse_prices = results["data_source"]
    else:
        source_label, reuse_prices = "new", None

    print(f"\nRunning {results['num_runs']} backtests for '{strategy.name}' "
          f"using {'reused' if source_label == 'reused' else 'newly generated'} price data...")

    result = run_backtest(
        strategy=strategy,
        price_params=price_params,
        starting_savings=results["starting_savings"],
        monthly_income=results["monthly_income"],
        num_runs=results["num_runs"],
        reuse_prices=reuse_prices,
    )

    show_dashboard(result, strategy.name)
    return result.price_series_used


def quick_run_flow() -> List[List[float]]:
    """
    Zero-prompt shortcut: runs a full backtest with every standard default
    (100€ start price, 50 years, 10,000€ starting savings, 300€/month,
    50 runs) against freshly generated data, using preset strategy #1
    (Buy Max Every Month). Useful for quickly sanity-checking the program
    after a code change without re-typing the same defaults every time.
    """
    price_params = PriceGeneratorParams(start_price=100.0, years=50)
    starting_savings, monthly_income = 10_000.0, 300.0
    num_runs = 50
    _, factory = presets.ALL_PRESETS["1"]
    strategy = factory()

    print(f"\nQuick Run: {strategy.name}, {num_runs} runs, new data, all standard defaults...")

    result = run_backtest(
        strategy=strategy,
        price_params=price_params,
        starting_savings=starting_savings,
        monthly_income=monthly_income,
        num_runs=num_runs,
        reuse_prices=None,
    )

    show_dashboard(result, strategy.name)
    return result.price_series_used


def run_bank_simulation_flow() -> None:
    print("\n-- Bank Balance Simulation --")
    steps: List[Tuple[str, Callable[[], Any]]] = [
        ("starting_balance", lambda: _ask_float("Starting balance (€)", 10_000.0)),
        ("monthly_deposit", lambda: _ask_float("Monthly deposit (€)", 300.0)),
        ("years", lambda: _ask_int("Years to simulate", 10)),
    ]
    results = _run_step_wizard(steps)
    result = run_bank_simulation(months=results["years"] * 12,
                                  starting_balance=results["starting_balance"],
                                  monthly_deposit=results["monthly_deposit"])
    print_bank_summary(result)


def main_menu() -> None:
    previous_prices: Optional[List[List[float]]] = None
    while True:
        print("\n" + "#" * 60)
        print(" INDEXING STRATEGY SIMULATOR")
        print("#" * 60)
        print(" 1. Run an investing strategy backtest")
        print(" 2. Quick Run (all defaults, new data, strategy #1)")
        print(" 3. Run a quick bank balance simulation")
        print(" 4. Exit")
        choice = input("Selection: ").strip()

        try:
            if choice == "1":
                previous_prices = run_investing_simulation_flow(previous_prices)
            elif choice == "2":
                previous_prices = quick_run_flow()
            elif choice == "3":
                run_bank_simulation_flow()
            elif choice == "4":
                print("Goodbye!")
                break
            else:
                print("Invalid selection, please try again.")
        except (_GoBack, _GoHome):
            # Backing out of the very first step of a flow, or explicitly
            # asking for the main menu, both land back here -- there's no
            # page "above" the main menu to distinguish them.
            print("\n(Returned to main menu.)")
            continue