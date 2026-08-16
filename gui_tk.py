"""
gui_tk.py

A Tkinter + ttk desktop GUI for the Indexing Strategy Simulator -- an
alternative front end to cli.py, aimed at people who'd rather click
through settings than type into a console. Everything here is a thin
layer over the exact same tested logic the CLI uses: price_generator.py,
strategy.py, backtest.py, presets.py, and dashboard.py (build_chart_figure
/ summary_groups) are all untouched and shared.

The whole window is the investing backtest -- no tabs, no bank simulation
panel (that was for testing only; a fixed-deposit savings account is a
simple enough calculation that it doesn't need a dedicated tool).

Themed with ttkbootstrap (a drop-in wrapper around ttk -- same widget
API) using a custom dark navy/cream theme defined in gui_theme.py. Window
background, panel colors, and the chart's colors are all sourced from
that same module's hex constants directly (not through ttkbootstrap's
bootstyle color roles) specifically so they're guaranteed to match
exactly, regardless of whether the custom theme registration itself
succeeds -- see gui_theme.create_and_register_theme()'s docstring for why
that's not 100% guaranteed to work on every ttkbootstrap version.

Run with:
    python gui_tk.py

IMPORTANT NOTE FOR WHOEVER FIRST RUNS THIS: this file was written without
being able to actually launch and see it (the development sandbox has no
tkinter/display available). The underlying calculations are exactly the
same proven code the CLI uses, but the widget layout, spacing, and any
Tkinter-specific wiring have NOT been visually verified. Please run it
and report anything that looks wrong or throws an error -- that's the
expected first step, not a sign something was rushed.
"""

import sys
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.dialogs import Messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from price_generator import PriceGeneratorParams
from backtest import run_backtest, compare_strategies
from dashboard import build_chart_figure, summary_groups
from strategy import Strategy, Rule, Trigger, Action
from market_events import MarketEvent
import presets
import gui_theme
from saved_strategies import (load_saved_strategies, save_strategies_to_disk,
                               MAX_SAVED_STRATEGIES, SAVED_STRATEGIES_PATH)


class CustomStrategyDialog(tk.Toplevel):
    """
    Modal dialog replicating cli.py's custom strategy builder: a
    multiplier per market event, plus optional escalating-streak rules
    for losing/gaining streaks. On OK, builds a Strategy and hands it back
    to the caller via `on_done(strategy)`; on Cancel, calls
    `on_cancel()` with nothing built.
    """

    def __init__(self, parent, on_done, on_cancel):
        super().__init__(parent)
        self.title("Custom Strategy Builder")
        self.resizable(False, False)
        # A tk.Toplevel's own window background is NOT automatically
        # themed by ttkbootstrap the way the main ttk.Window is -- ttk
        # widgets placed inside it pick up the global style, but the raw
        # Toplevel background itself does not unless set explicitly. This
        # was the direct cause of the white background around the dialog.
        self.configure(background=gui_theme.CHART_BG)
        self.transient(parent)
        self.grab_set()  # modal: blocks interaction with the main window until closed

        self._on_done = on_done
        self._on_cancel = on_cancel
        self._event_vars: dict = {}

        pad = {"padx": 10, "pady": 3}

        ttk.Label(self, text="Multiplier per market event", font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 2))
        ttk.Label(self, text="(1 = no change, 2 = double, 0.5 = half, 0 = skip; blank = unaffected)",
                  font=("", 8)).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))

        row = 2
        for event in MarketEvent:
            ttk.Label(self, text=event.value).grid(row=row, column=0, sticky="w", **pad)
            var = tk.StringVar()
            ttk.Entry(self, textvariable=var, width=10).grid(row=row, column=1, sticky="e", **pad)
            self._event_vars[event] = var
            row += 1

        ttk.Separator(self, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=8)
        row += 1

        ttk.Label(self, text="Escalate on losing streak", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1
        ttk.Label(self, text="Multiplier increase / extra month (blank = off)").grid(
            row=row, column=0, sticky="w", **pad)
        self.loss_increment_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.loss_increment_var, width=10).grid(row=row, column=1, sticky="e", **pad)
        row += 1
        ttk.Label(self, text="Cap the multiplier at (blank = no cap)").grid(row=row, column=0, sticky="w", **pad)
        self.loss_cap_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.loss_cap_var, width=10).grid(row=row, column=1, sticky="e", **pad)
        row += 1

        ttk.Separator(self, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=8)
        row += 1

        ttk.Label(self, text="Escalate on gaining streak", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1
        ttk.Label(self, text="Multiplier increase / extra month (blank = off)").grid(
            row=row, column=0, sticky="w", **pad)
        self.gain_increment_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.gain_increment_var, width=10).grid(row=row, column=1, sticky="e", **pad)
        row += 1
        ttk.Label(self, text="Cap the multiplier at (blank = no cap)").grid(row=row, column=0, sticky="w", **pad)
        self.gain_cap_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.gain_cap_var, width=10).grid(row=row, column=1, sticky="e", **pad)
        row += 1

        ttk.Separator(self, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=8)
        row += 1

        ttk.Label(self, text="Strategy name").grid(row=row, column=0, sticky="w", **pad)
        self.name_var = tk.StringVar(value="Custom Strategy")
        ttk.Entry(self, textvariable=self.name_var, width=22).grid(row=row, column=1, sticky="e", **pad)
        row += 1

        ttk.Label(self, text="Description (optional) \u2014 shown next to results",
                  font=("", 8)).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 2))
        row += 1
        self.description_text = tk.Text(self, width=38, height=4, wrap="word",
                                         background=gui_theme.BG_CARD, foreground=gui_theme.TEXT_CREAM,
                                         insertbackground=gui_theme.TEXT_CREAM, relief="flat")
        self.description_text.grid(row=row, column=0, columnspan=2, padx=10, pady=(0, 4))
        row += 1

        self.save_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text=f"Save this strategy (up to {MAX_SAVED_STRATEGIES}, available "
                                    f"from the dropdown for this session only)",
                        variable=self.save_var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 0))
        row += 1

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=14)
        ttk.Button(btn_frame, text="OK", command=self._handle_ok, style="Success.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self._handle_cancel, style="Danger.TButton").pack(side=tk.LEFT, padx=6)

        self.protocol("WM_DELETE_WINDOW", self._handle_cancel)

        # Applied at the END of __init__ (all widgets/geometry already
        # built) and deferred via after() rather than called immediately --
        # this Toplevel's native OS window may not be fully realized yet
        # at the moment __init__ runs, and DWM attribute changes are known
        # to be unreliable if applied before that. Also switched from
        # GetParent() to GetAncestor(GA_ROOT) in the helper itself, which
        # is the more robust API for finding a window's true top-level
        # handle -- both changes together, since I can't isolate which one
        # was the actual issue without a Windows environment to test in.
        self.after(10, lambda: _apply_windows_dark_titlebar(self))

    def _parse_optional_float(self, raw: str, field_label: str):
        """Returns (value, ok). value is None if blank; shows an error and ok=False if invalid."""
        raw = raw.strip()
        if raw == "":
            return None, True
        try:
            return float(raw), True
        except ValueError:
            Messagebox.show_error(message=f"'{raw}' is not a valid number for {field_label}.",
                                   title="Invalid input", parent=self)
            return None, False

    def _handle_ok(self):
        rules = []

        for event, var in self._event_vars.items():
            value, ok = self._parse_optional_float(var.get(), event.value)
            if not ok:
                return
            if value is not None:
                rules.append(Rule(Trigger(type="event", event=event), Action(type="multiply", value=value)))

        loss_increment, ok = self._parse_optional_float(self.loss_increment_var.get(), "loss escalation increment")
        if not ok:
            return
        if loss_increment is not None:
            loss_cap, ok = self._parse_optional_float(self.loss_cap_var.get(), "loss escalation cap")
            if not ok:
                return
            rules.append(Rule(Trigger(type="sequential_loss", streak=1),
                               Action(type="scale_with_streak", start=1.0, increment=loss_increment, cap=loss_cap)))

        gain_increment, ok = self._parse_optional_float(self.gain_increment_var.get(), "gain escalation increment")
        if not ok:
            return
        if gain_increment is not None:
            gain_cap, ok = self._parse_optional_float(self.gain_cap_var.get(), "gain escalation cap")
            if not ok:
                return
            rules.append(Rule(Trigger(type="sequential_gain", streak=1),
                               Action(type="scale_with_streak", start=1.0, increment=gain_increment, cap=gain_cap)))

        name = self.name_var.get().strip() or "Custom Strategy"
        description = self.description_text.get("1.0", "end-1c").strip()
        strategy = Strategy(name=name, rules=rules, description=description)
        save = self.save_var.get()
        self.destroy()
        self._on_done(strategy, save)

    def _handle_cancel(self):
        self.destroy()
        self._on_cancel()


class SimulatorApp:
    """Main application window: the investing backtest, no tabs."""

    PRESET_NAMES = [name for _key, (name, _factory) in presets.ALL_PRESETS.items()]
    CUSTOM_LABEL = "Custom..."
    DATA_SOURCE_NEW = "Generate new data"
    DATA_SOURCE_REUSE = "Reuse previous run's data"

    def __init__(self, root: "ttk.Window"):
        self.root = root
        self.root.title("Indexing Strategy Simulator")
        self.root.geometry("1500x850")
        self.root.minsize(1100, 650)

        self.previous_prices = None      # for "reuse previous data"
        self.custom_strategy = None      # set by CustomStrategyDialog
        self.current_fig = None          # tracks the live matplotlib Figure so we can plt.close() it on refresh
        self._last_single_result = None  # (result, name, description) of the last single-strategy run, for restoring after Compare All
        self.chart_scale = "linear"      # toggled by the log/linear button, bottom of settings
        # Loaded once at startup; a corrupted/missing save file returns []
        # rather than crashing (see saved_strategies.load_saved_strategies).
        self.saved_strategies = load_saved_strategies()

        # No Notebook -- this is the only content, so the tab strip would
        # just be wasted vertical space for a single tab.
        content = ttk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True)
        self._build_main_content(content)

    # ---------------------------------------------------------------
    # Main content
    # ---------------------------------------------------------------

    def _build_main_content(self, parent: ttk.Frame) -> None:
        # Layout uses plain pack() with FIXED PIXEL widths for the settings
        # and output panels, with the chart taking whatever space is left
        # via expand=True -- deliberately simple rather than trying to
        # hold an exact percentage split across every window size (which
        # would need grid weight/proportional-sizing logic). Output
        # (440px) is intentionally wider than settings (220px).
        SETTINGS_WIDTH_PX = 220
        OUTPUT_WIDTH_PX = 440
        SPACER_PX = 6
        self.SETTINGS_WIDTH_PX = SETTINGS_WIDTH_PX
        self.OUTPUT_WIDTH_PX = OUTPUT_WIDTH_PX
        self.SPACER_PX = SPACER_PX
        self.compare_mode = False  # True while the wide table/graph layout is active
        self.compare_view = None   # "table" or "graph", which content the wide panel currently shows
        self._last_compare_rows = None  # cached Compare All results, so toggling back to "table" doesn't re-run backtests
        self._last_compare_market_result = None  # the shared price data all compared strategies were tested against
        self._compare_graph_fig = None  # tracks the compare-mode graph Figure so we can plt.close() it on refresh

        settings = ttk.Frame(parent, padding=8, width=SETTINGS_WIDTH_PX)
        settings.pack(side=tk.LEFT, fill=tk.Y)
        settings.pack_propagate(False)  # lock at the fixed width regardless of content
        settings.columnconfigure(0, weight=0)
        settings.columnconfigure(1, weight=1)

        ttk.Frame(parent, width=SPACER_PX).pack(side=tk.LEFT, fill=tk.Y)

        self.chart_frame = ttk.Frame(parent)
        self.chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)  # takes all remaining space
        # This is required even though chart_frame uses expand=True rather
        # than a fixed width -- without it, the matplotlib canvas's large
        # natural size (~900x650px, from its fixed figsize) inflates
        # chart_frame's own requested size once a real chart is rendered,
        # which then affects how pack() calculates space for every widget
        # packed AFTER it -- including the fixed-width output panel below.
        self.chart_frame.pack_propagate(False)

        ttk.Frame(parent, width=SPACER_PX).pack(side=tk.LEFT, fill=tk.Y)

        self.stats_container = ttk.Frame(parent, width=OUTPUT_WIDTH_PX)
        self.stats_container.pack(side=tk.LEFT, fill=tk.Y)
        self.stats_container.pack_propagate(False)  # lock at the fixed width regardless of content

        pad = {"sticky": "w", "pady": 2}
        row = 0

        def panel_title(title: str) -> None:
            """Large 20px title for a whole panel -- "Settings" here,
            "Output" on the results side (see _render_stats_card). Kept
            visually distinct from section()'s smaller subsection headers
            (e.g. "Investing"), which sit one level below it."""
            nonlocal row
            ttk.Label(settings, text=title, font=("", 20, "bold")).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(4, 6))
            row += 1

        def section(title: str) -> None:
            nonlocal row
            ttk.Label(settings, text=title, font=("", 16, "bold")).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(10, 3))
            row += 1

        def separator() -> None:
            nonlocal row
            ttk.Separator(settings, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=6)
            row += 1

        # Consolidated from 5 sections down to 2, as requested: "Settings"
        # covers the run's mechanics (price, horizon, run count, data
        # source); "Investing" covers the money side (savings, income,
        # strategy) -- a cleaner split than the original 5 narrow groups.
        panel_title("Settings")
        ttk.Label(settings, text="Start price (€)", font=("", 14)).grid(row=row, column=0, **pad)
        self.start_price_var = tk.StringVar(value="100")
        ttk.Entry(settings, textvariable=self.start_price_var, width=12, font=("", 14)).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(settings, text="Years", font=("", 14)).grid(row=row, column=0, **pad)
        self.years_var = tk.StringVar(value="50")
        ttk.Entry(settings, textvariable=self.years_var, width=12, font=("", 14)).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(settings, text="Number of runs", font=("", 14)).grid(row=row, column=0, **pad)
        self.num_runs_var = tk.StringVar(value="50")
        ttk.Entry(settings, textvariable=self.num_runs_var, width=12, font=("", 14)).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(settings, text="Data source", font=("", 14)).grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        row += 1
        # A Combobox instead of two Radiobuttons -- ttkbootstrap's radio
        # indicator circle size isn't something exposed as a simple style
        # option (it's baked into internally-generated theme images), so
        # rather than a fragile custom-image hack I can't visually verify,
        # this sidesteps the sizing question entirely and matches the
        # Strategy dropdown's existing style below.
        self.data_source_var = tk.StringVar(value=self.DATA_SOURCE_NEW)
        ttk.Combobox(settings, textvariable=self.data_source_var,
                     values=[self.DATA_SOURCE_NEW, self.DATA_SOURCE_REUSE],
                     state="readonly", width=30, font=("", 14)).grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1

        separator()
        section("Investing")
        ttk.Label(settings, text="Starting savings (€)", font=("", 14)).grid(row=row, column=0, **pad)
        self.savings_var = tk.StringVar(value="10000")
        ttk.Entry(settings, textvariable=self.savings_var, width=12, font=("", 14)).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(settings, text="Monthly income (€)", font=("", 14)).grid(row=row, column=0, **pad)
        self.income_var = tk.StringVar(value="300")
        ttk.Entry(settings, textvariable=self.income_var, width=12, font=("", 14)).grid(row=row, column=1, sticky="ew")
        row += 1

        ttk.Label(settings, text="Strategy", font=("", 14)).grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        row += 1
        self.strategy_var = tk.StringVar(value=self.PRESET_NAMES[0])
        self.strategy_combo = ttk.Combobox(settings, textvariable=self.strategy_var,
                                            values=self._build_strategy_dropdown_values(),
                                            state="readonly", width=30, font=("", 14))
        self.strategy_combo.grid(row=row, column=0, columnspan=2, sticky="ew")
        self.strategy_combo.bind("<<ComboboxSelected>>", self._on_strategy_selected)
        row += 1
        # bootstyle removed entirely here too -- same risk class as the
        # buttons below, and this label needs a custom font (8pt), so it's
        # simplest to just drop the "info" accent color and use a plain
        # Label (which font=... has always worked fine on, confirmed by
        # every OTHER plain label in this panel never crashing).
        self.custom_strategy_status = ttk.Label(settings, text="", font=("", 8))
        self.custom_strategy_status.grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        # NOTE: font is NOT set anywhere on either button instance below
        # (neither constructor nor .configure()). Confirmed via two real
        # tracebacks that ttkbootstrap's bootstyle-processing layer raises
        # "_tkinter.TclError: unknown option -font" whenever font is set
        # directly on a bootstyle/custom-style widget, in any form. Font
        # is baked into the "Primary.TButton"/"Accent.TButton" style
        # definitions themselves instead (see main()) -- a different code
        # path that isn't affected by whatever is broken here.
        separator()
        ttk.Button(settings, text="Run Backtest", command=self._on_run_backtest,
                   style="Primary.TButton").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(6, 3))
        row += 1
        ttk.Button(settings, text="Quick Run (all defaults)", command=self._on_quick_run,
                   style="Accent.TButton").grid(
            row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        ttk.Button(settings, text="Compare All", command=self._on_compare_all,
                   style="Compare.TButton").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        row += 1
        # Lives in the settings panel rather than on the table itself, so
        # it's always in a predictable place. Created once, hidden by
        # default (grid_remove keeps its grid slot reserved for when it's
        # shown again, unlike grid_forget which would lose that
        # placement); _enter_compare_mode / _restore_normal_layout toggle
        # it with .grid()/.grid_remove().
        self.switch_to_graph_button = ttk.Button(
            settings, text="Switch to Graph", command=self._on_toggle_compare_view,
            style="SwitchGraph.TButton")
        self.switch_to_graph_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        self.switch_to_graph_button.grid_remove()
        row += 1

        # Spacer row: absorbs all leftover vertical space in the settings
        # panel, pushing the chart-scale toggle down to the actual bottom
        # of the panel instead of it just sitting directly under Compare
        # All with unused space below it. No other row in this grid has a
        # nonzero weight, so this one row claims 100% of any extra height
        # settings.grid()'s "nsew" sticky gives it beyond what the buttons
        # above need.
        settings.rowconfigure(row, weight=1)
        ttk.Frame(settings).grid(row=row, column=0, columnspan=2, sticky="nsew")
        row += 1

        # Always visible (unlike Switch to Graph, which only shows during
        # Compare mode) -- applies to whichever chart is currently on
        # screen, single-strategy or Compare mode's market chart. Sits at
        # the very bottom of the settings panel (see spacer row above).
        self.chart_scale_button = ttk.Button(
            settings, text="View Log Graph", command=self._on_toggle_chart_scale,
            style="SwitchGraph.TButton")
        self.chart_scale_button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        row += 1

        self.chart_placeholder = ttk.Label(
            self.chart_frame,
            text="Welcome\n\nConfigure settings on the left and click 'Run Backtest'\n"
                 "(or just 'Quick Run') to see results here.",
            font=("", 14), justify="center", padding=40)
        self.chart_placeholder.pack(expand=True)

        # "Output" title visible immediately, same as "Settings" -- the
        # panel structure is consistent from the start, not just once a
        # backtest has run.
        initial_card = ttk.Frame(self.stats_container, padding=10)
        initial_card.pack(fill=tk.BOTH, expand=True)
        ttk.Label(initial_card, text="Output", font=("", 20, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(initial_card, text="Results will appear here after running a backtest.",
                  font=("", 14), wraplength=390, justify="left").pack(anchor="w")

    def _build_strategy_dropdown_values(self) -> list:
        return self.PRESET_NAMES + [s.name for s in self.saved_strategies] + [self.CUSTOM_LABEL]

    def _on_strategy_selected(self, _event=None) -> None:
        if self.strategy_var.get() == self.CUSTOM_LABEL:
            CustomStrategyDialog(self.root, on_done=self._on_custom_strategy_done,
                                  on_cancel=self._on_custom_strategy_cancelled)

    def _on_custom_strategy_done(self, strategy: Strategy, save: bool = False) -> None:
        self.custom_strategy = strategy
        self.custom_strategy_status.config(text=f"\u2713 '{strategy.name}' ({len(strategy.rules)} rule(s) set)")

        if save:
            if len(self.saved_strategies) >= MAX_SAVED_STRATEGIES:
                Messagebox.show_error(
                    message=f"You can save up to {MAX_SAVED_STRATEGIES} custom strategies, and that "
                            f"limit has been reached. This strategy is still usable for this session "
                            f"via 'Custom...', just not saved to the dropdown.",
                    title="Save limit reached")
                return
            self.saved_strategies.append(strategy)
            save_strategies_to_disk(self.saved_strategies)
            self.strategy_combo.configure(values=self._build_strategy_dropdown_values())
            # Select the newly-saved strategy directly, rather than leaving
            # the dropdown on "Custom..." now that it has its own entry.
            self.strategy_var.set(strategy.name)

    def _on_custom_strategy_cancelled(self) -> None:
        # if no custom strategy was ever successfully built, fall back to the first preset
        # rather than leaving the dropdown pointed at an unconfigured "Custom..."
        if self.custom_strategy is None:
            self.strategy_var.set(self.PRESET_NAMES[0])

    def _get_selected_strategy(self):
        name = self.strategy_var.get()
        if name == self.CUSTOM_LABEL:
            if self.custom_strategy is None:
                Messagebox.show_error(message="Select 'Custom...' again and fill in the dialog first.",
                                       title="No custom strategy configured")
                return None
            return self.custom_strategy
        for _key, (preset_name, factory) in presets.ALL_PRESETS.items():
            if preset_name == name:
                return factory()
        for saved in self.saved_strategies:
            if saved.name == name:
                return saved
        return None  # should be unreachable given the dropdown is read-only

    def _parse_investing_inputs(self):
        """Returns a dict of parsed values, or None (after showing an error) if anything is invalid."""
        try:
            start_price = float(self.start_price_var.get())
            years = int(self.years_var.get())
            starting_savings = float(self.savings_var.get())
            monthly_income = float(self.income_var.get())
            num_runs = int(self.num_runs_var.get())
        except ValueError:
            Messagebox.show_error(message="Please make sure every field contains a valid number.",
                                   title="Invalid input")
            return None

        if start_price <= 0 or years <= 0 or num_runs <= 0:
            Messagebox.show_error(message="Start price, years, and number of runs must all be positive.",
                                   title="Invalid input")
            return None

        return {
            "start_price": start_price, "years": years,
            "starting_savings": starting_savings, "monthly_income": monthly_income,
            "num_runs": num_runs,
        }

    def _on_run_backtest(self) -> None:
        inputs = self._parse_investing_inputs()
        if inputs is None:
            return
        strategy = self._get_selected_strategy()
        if strategy is None:
            return

        wants_reuse = self.data_source_var.get() == self.DATA_SOURCE_REUSE
        if wants_reuse and self.previous_prices is None:
            Messagebox.show_error(
                message="No previous run to reuse yet -- run once with 'Generate new data' first.",
                title="No previous data")
            return

        price_params = PriceGeneratorParams(start_price=inputs["start_price"], years=inputs["years"])
        reuse = self.previous_prices if wants_reuse else None

        result = run_backtest(
            strategy=strategy, price_params=price_params,
            starting_savings=inputs["starting_savings"], monthly_income=inputs["monthly_income"],
            num_runs=inputs["num_runs"], reuse_prices=reuse,
        )
        self.previous_prices = result.price_series_used
        self._restore_normal_layout()  # in case this was clicked while Compare All's table was showing
        self._render_investing_results(result, strategy.name, strategy.description)

    def _on_quick_run(self) -> None:
        """Mirrors cli.py's Quick Run: every standard default, new data, preset #1."""
        _name, factory = presets.ALL_PRESETS["1"]
        strategy = factory()
        price_params = PriceGeneratorParams(start_price=100.0, years=50)
        result = run_backtest(strategy=strategy, price_params=price_params,
                               starting_savings=10_000.0, monthly_income=300.0,
                               num_runs=50, reuse_prices=None)
        self.previous_prices = result.price_series_used
        self._restore_normal_layout()  # in case this was clicked while Compare All's table was showing
        self._render_investing_results(result, strategy.name, strategy.description)

    def _on_compare_all(self) -> None:
        inputs = self._parse_investing_inputs()
        if inputs is None:
            return

        # Every preset, plus the custom strategy if one has been configured.
        strategies = [factory() for _name, factory in presets.ALL_PRESETS.values()]
        if self.custom_strategy is not None:
            strategies.append(self.custom_strategy)

        price_params = PriceGeneratorParams(start_price=inputs["start_price"], years=inputs["years"])
        try:
            rows, market_result = compare_strategies(
                strategies, price_params,
                starting_savings=inputs["starting_savings"], monthly_income=inputs["monthly_income"],
                num_runs=inputs["num_runs"],
            )
            self._last_compare_rows = rows
            self._last_compare_market_result = market_result
            self._enter_compare_mode()
            self._show_compare_table()
        except Exception as exc:
            # A Tkinter callback exception otherwise gets swallowed by the
            # event loop -- printed to the console only, with the UI left
            # in whatever partial state it reached when the exception hit.
            # Surfacing the error directly and reverting to a known-good
            # layout state is far more useful than a silent failure.
            Messagebox.show_error(message=f"Compare All failed:\n{exc}", title="Error")
            self._restore_normal_layout()

    def _enter_compare_mode(self) -> None:
        """
        Hides the chart, widens the output panel to fill the space both
        the chart and the normal output panel used to occupy -- the wide
        single-panel layout shared by BOTH the table and (when toggled)
        the graph while in Compare mode. Idempotent: does nothing if
        already in this mode, since _on_compare_all can be clicked again
        to refresh the table without needing to re-widen anything.
        """
        if self.compare_mode:
            return
        self.compare_mode = True
        self.chart_frame.pack_forget()

        self.stats_container.pack_forget()
        # Width AND height computed explicitly from the window's CURRENT
        # size at the moment Compare All is clicked -- not dynamically
        # responsive to later resizes. Fixed sizing at click-time was
        # chosen over responsive/dynamic sizing for reliability -- Tk's
        # geometry recalculation on every resize event is a much larger
        # source of edge cases than a size that's simply fixed once.
        total_width = self.root.winfo_width()
        total_height = self.root.winfo_height()
        table_width = max(500, total_width - self.SETTINGS_WIDTH_PX - 2 * self.SPACER_PX - 20)
        table_height = max(400, total_height - 20)
        self.stats_container.configure(width=table_width, height=table_height)
        self.stats_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.switch_to_graph_button.grid()  # show it (was grid_remove()-d by default)

    def _restore_normal_layout(self) -> None:
        """Fully exits Compare mode back to the narrow 3-panel layout
        (settings | chart | narrow output). Used when a genuinely new
        single-strategy run is requested (Run Backtest / Quick Run) or
        Compare All itself fails -- NOT used by the in-mode table/graph
        toggle, which stays in the wide layout the whole time."""
        if not self.compare_mode:
            return
        self.compare_mode = False
        self.compare_view = None
        if self._compare_graph_fig is not None:
            plt.close(self._compare_graph_fig)
            self._compare_graph_fig = None
        self.stats_container.pack_forget()
        # chart_frame must be re-packed BEFORE stats_container -- chart_frame
        # was left unpacked since entering compare mode, so re-adding
        # stats_container first would insert it ahead of chart_frame in
        # the pack order (settings, output, chart instead of settings,
        # chart, output).
        self.chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.stats_container.configure(width=self.OUTPUT_WIDTH_PX)
        self.stats_container.pack(side=tk.LEFT, fill=tk.Y)
        self.switch_to_graph_button.grid_remove()
        self.switch_to_graph_button.configure(text="Switch to Graph")

    def _on_toggle_compare_view(self) -> None:
        """The single button toggles between the table and graph views,
        both rendered INSIDE the same wide stats_container -- chart_frame
        stays hidden the whole time, per "only Settings and Output (now
        widened) should be visible" while in Compare mode."""
        if self.compare_view == "table":
            self._show_compare_graph()
        else:
            self._show_compare_table()

    def _on_toggle_chart_scale(self) -> None:
        """Applies to whichever chart is currently visible -- the normal
        single-strategy chart, or Compare mode's market-data graph.
        Rebuilding via the existing render methods (rather than trying to
        mutate a live Axes' scale in place) reuses already-tested code and
        keeps this simple, at the cost of a full chart rebuild rather than
        an in-place scale swap -- cheap enough not to matter here."""
        self.chart_scale = "log" if self.chart_scale == "linear" else "linear"
        self.chart_scale_button.configure(
            text="View Linear Graph" if self.chart_scale == "log" else "View Log Graph")

        if self.compare_mode and self.compare_view == "graph":
            self._show_compare_graph()
        elif not self.compare_mode and self._last_single_result is not None:
            result, name, description = self._last_single_result
            self._render_investing_results(result, name, description)

    def _show_compare_table(self) -> None:
        self.compare_view = "table"
        self.switch_to_graph_button.configure(text="Switch to Graph")
        self._render_comparison_table(self._last_compare_rows)

    def _show_compare_graph(self) -> None:
        self.compare_view = "graph"
        self.switch_to_graph_button.configure(text="Switch to Table")

        for widget in self.stats_container.winfo_children():
            widget.destroy()

        header_frame = ttk.Frame(self.stats_container, padding=(10, 10, 10, 4))
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text="Data Used for Comparison", font=("", 20, "bold")).pack(side=tk.LEFT)

        if self._compare_graph_fig is not None:
            plt.close(self._compare_graph_fig)
            self._compare_graph_fig = None

        if self._last_compare_market_result is not None:
            # Built from the SAME shared price data every strategy in the
            # table was tested against (see compare_strategies' market_result
            # return value) -- NOT self.current_fig, which was the wrong
            # thing here: that's whatever the last independent single-
            # strategy run happened to be, unrelated to this comparison.
            chart_area = ttk.Frame(self.stats_container)
            chart_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
            fig = build_chart_figure(self._last_compare_market_result,
                                      "Data Used for Comparison", dark_mode=True,
                                      y_scale=self.chart_scale)
            self._compare_graph_fig = fig
            canvas = FigureCanvasTkAgg(fig, master=chart_area)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(self.stats_container,
                      text="No comparison data yet -- click 'Compare All' first.",
                      justify="center", padding=40).pack(expand=True)

    MAX_STRATEGY_NAME_CHARS = 28

    def _render_comparison_table(self, rows: list) -> None:
        """
        Builds the "Compare All" table as a grid of individually colorable
        ttk.Label widgets -- NOT a ttk.Treeview. Treeview only supports
        coloring a whole ROW via tags; this needs to color SPECIFIC CELLS
        (return, drawdown) independently based on their own rank, which
        Treeview has no built-in way to do.

        No scrolling: the table (max ~13 rows: 12 presets + 1 custom)
        comfortably fits the available space, and a scrollbar was showing
        up even when entirely unnecessary -- removed per explicit
        request rather than continuing to debug the scrollregion
        calculation.
        """
        for widget in self.stats_container.winfo_children():
            widget.destroy()

        header_frame = ttk.Frame(self.stats_container, padding=(10, 10, 10, 4))
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text="Compare All", font=("", 20, "bold")).pack(side=tk.LEFT)

        inner = ttk.Frame(self.stats_container, padding=(10, 0, 10, 10))
        inner.pack(fill=tk.BOTH, expand=True)

        columns = [
            ("Strategy", "w", 3),
            ("Total Return", "center", 1),
            ("Annualized", "center", 1),
            ("Capital Efficiency", "center", 1),
            ("Ending Value", "center", 1),
            ("Max Drawdown", "center", 1),
            ("Gap to Best", "center", 1),
        ]
        for col_idx, (_label, _anchor, weight) in enumerate(columns):
            inner.columnconfigure(col_idx, weight=weight)

        header_row = 0
        for col_idx, (label, anchor, _weight) in enumerate(columns):
            ttk.Label(inner, text=label, font=("", 12, "bold"), anchor=anchor).grid(
                row=header_row, column=col_idx, sticky="ew", padx=6, pady=(4, 8))
        ttk.Separator(inner, orient="horizontal").grid(
            row=header_row + 1, column=0, columnspan=len(columns), sticky="ew", padx=6)

        total = len(rows)
        drawdowns = [r["median_max_drawdown_pct"] for r in rows]
        # Drawdown ranking is separate from the return-based row order:
        # smaller (less negative) drawdown is "better" here, so rank by
        # drawdown descending (closest to zero first) independent of
        # whichever position that row happens to sit at in the table.
        drawdown_order = sorted(range(total), key=lambda i: drawdowns[i], reverse=True)
        drawdown_rank = {row_i: rank for rank, row_i in enumerate(drawdown_order)}

        # Capital efficiency ranking is ALSO independent of the return-
        # based row order -- two strategies can have very different total
        # returns (one uses far more capital) while sharing near-identical
        # efficiency (same underlying buy pattern, just different scale),
        # so this needs its own ranking, not a reuse of the return rank.
        efficiencies = [r["median_capital_efficiency_pct"] for r in rows]
        efficiency_order = sorted(range(total), key=lambda i: efficiencies[i], reverse=True)
        efficiency_rank = {row_i: rank for rank, row_i in enumerate(efficiency_order)}

        for i, row_data in enumerate(rows):
            grid_row = header_row + 2 + i

            name = row_data["name"]
            if len(name) > self.MAX_STRATEGY_NAME_CHARS:
                name = name[: self.MAX_STRATEGY_NAME_CHARS - 1] + "\u2026"
            ttk.Label(inner, text=name, font=("", 12), anchor="w", justify="left").grid(
                row=grid_row, column=0, sticky="w", padx=6, pady=4)

            return_color = gui_theme.get_rank_color(i, total)
            return_font = ("", 12, "bold") if return_color else ("", 12)
            return_label = ttk.Label(inner, text=f"{row_data['median_return_pct']:.2f}%",
                                      font=return_font, anchor="center")
            if return_color:
                return_label.configure(foreground=return_color)
            return_label.grid(row=grid_row, column=1, sticky="ew", padx=6, pady=4)

            ttk.Label(inner, text=f"{row_data['median_annual_return_pct']:.2f}%",
                      font=("", 12), anchor="center").grid(row=grid_row, column=2, sticky="ew", padx=6, pady=4)

            eff_color = gui_theme.get_rank_color(efficiency_rank[i], total)
            eff_font = ("", 12, "bold") if eff_color else ("", 12)
            eff_label = ttk.Label(inner, text=f"{row_data['median_capital_efficiency_pct']:.2f}%",
                                   font=eff_font, anchor="center")
            if eff_color:
                eff_label.configure(foreground=eff_color)
            eff_label.grid(row=grid_row, column=3, sticky="ew", padx=6, pady=4)

            ttk.Label(inner, text=f"\u20ac{row_data['median_ending_portfolio_value']:,.0f}",
                      font=("", 12), anchor="center").grid(row=grid_row, column=4, sticky="ew", padx=6, pady=4)

            dd_color = gui_theme.get_rank_color(drawdown_rank[i], total)
            dd_font = ("", 12, "bold") if dd_color else ("", 12)
            dd_label = ttk.Label(inner, text=f"{row_data['median_max_drawdown_pct']:.2f}%",
                                  font=dd_font, anchor="center")
            if dd_color:
                dd_label.configure(foreground=dd_color)
            dd_label.grid(row=grid_row, column=5, sticky="ew", padx=6, pady=4)

            gap_text = "\u2014" if row_data["return_gap_pct"] == 0 else f"-{row_data['return_gap_pct']:.2f}%"
            ttk.Label(inner, text=gap_text, font=("", 12), anchor="center").grid(
                row=grid_row, column=6, sticky="ew", padx=6, pady=4)

    def _render_investing_results(self, result, strategy_name: str, strategy_description: str = "") -> None:
        self._last_single_result = (result, strategy_name, strategy_description)
        for widget in self.chart_frame.winfo_children():
            widget.destroy()
        if self.current_fig is not None:
            plt.close(self.current_fig)  # release the previous figure's memory

        fig = build_chart_figure(result, strategy_name, figsize=(9.0, 6.5), dark_mode=True,
                                  y_scale=self.chart_scale)
        self.current_fig = fig
        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._render_stats_card(self.stats_container, strategy_name, strategy_description, result)

    def _render_stats_card(self, container, strategy_name: str, strategy_description: str, result) -> None:
        """
        Builds the results panel as a real "card" of ttk widgets (a
        colored Frame + Label/value rows) instead of a monospace Text
        buffer -- fixes both the cramped/scrolling width AND the
        terminal-like look, since real proportional-font labels replace
        hand-padded Courier strings entirely.
        """
        for widget in container.winfo_children():
            widget.destroy()

        # No bootstyle="secondary" here (that was an earlier two-tone
        # "card" design) -- plain Frames/Labels inherit the theme's
        # default bg/fg directly, so this matches the settings panel's
        # background and text color exactly, as requested.
        # Single margin source (card's own padding) instead of the
        # previous container-pack-margin + card-padding stacking on top
        # of each other, which was adding unnecessary empty space.
        card = ttk.Frame(container, padding=10)
        card.pack(fill=tk.BOTH, expand=True)

        # Output is a fixed 440px (OUTPUT_WIDTH_PX in _build_main_content),
        # so wrap_px can be calculated directly against that number.
        # 440 - 2*10 (card padding) = 420 usable; small margin for safety.
        wrap_px = 390

        # Matches the settings panel's "Settings" title style, for a
        # consistent look between the two panels.
        ttk.Label(card, text="Output", font=("", 20, "bold")).pack(anchor="w", pady=(0, 8))

        ttk.Label(card, text=strategy_name, font=("", 16, "bold"),
                  wraplength=wrap_px, justify="left").pack(anchor="w", pady=(0, 6))

        if strategy_description:
            ttk.Label(card, text=strategy_description, font=("", 14),
                      wraplength=wrap_px, justify="left").pack(anchor="w", pady=(0, 12))

        for group_title, rows in summary_groups(result):
            if group_title is not None:
                ttk.Separator(card, orient="horizontal").pack(fill=tk.X, pady=(10, 5))
                ttk.Label(card, text=group_title, font=("", 16, "bold")).pack(anchor="w", pady=(0, 3))
            for label, value, raw in rows:
                row = ttk.Frame(card)
                row.pack(fill=tk.X, pady=2)
                ttk.Label(row, text=label, font=("", 14)).pack(side=tk.LEFT)

                if isinstance(raw, tuple):
                    # IQR-style row: two numbers in one cell ("-31.0% to
                    # 139.2%"). Colored by POSITION, not by each number's
                    # own sign -- the low (worse) end is always the
                    # "negative" red, the high (better) end always the
                    # "positive" green, even in an edge case where the low
                    # end happens to still be a positive number. Reformats
                    # directly from the raw numbers rather than parsing the
                    # pre-built `value` string back apart, so this can't
                    # drift out of sync with summary_groups()'s formatting.
                    low_raw, high_raw = raw
                    value_frame = ttk.Frame(row)
                    ttk.Label(value_frame, text=f"{low_raw:.1f}%", font=("", 14, "bold"),
                              foreground=gui_theme.OUTPUT_NEGATIVE).pack(side=tk.LEFT)
                    ttk.Label(value_frame, text=" to ", font=("", 14, "bold")).pack(side=tk.LEFT)
                    ttk.Label(value_frame, text=f"{high_raw:.1f}%", font=("", 14, "bold"),
                              foreground=gui_theme.OUTPUT_POSITIVE).pack(side=tk.LEFT)
                    value_frame.pack(side=tk.RIGHT)
                else:
                    value_label = ttk.Label(row, text=value, font=("", 14, "bold"))
                    if raw is not None:
                        # Sign-based color from the RAW number, not the
                        # formatted string -- avoids any parsing fragility
                        # (e.g. "-0.00%" edge cases) and stays correct if
                        # the formatting ever changes.
                        color = gui_theme.OUTPUT_POSITIVE if raw >= 0 else gui_theme.OUTPUT_NEGATIVE
                        value_label.configure(foreground=color)
                    value_label.pack(side=tk.RIGHT)


def _apply_windows_dark_titlebar(root) -> None:
    """
    Best-effort: asks Windows to draw the window's native title bar (the
    minimize/maximize/close bar, drawn by the OS -- not by Tkinter/ttk/
    ttkbootstrap, which have no cross-platform way to theme it at all) in
    dark mode, via the documented DWMWA_USE_IMMERSIVE_DARK_MODE window
    attribute (Windows 10 20H1+ / Windows 11).

    Windows-only: a no-op (silently returns) on any other platform.
    Best-effort even on Windows: wrapped in try/except so a failure here
    (wrong attribute value for an older Windows build, DWM unavailable,
    anything) never prevents the app from starting -- this is cosmetic,
    not load-bearing. NOT verified to actually render correctly; this
    sandbox has no Windows environment to test it in.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        root.update_idletasks()  # ensure the window handle actually exists yet
        # GetAncestor(hwnd, GA_ROOT) reliably walks up to the true
        # top-level window handle -- switched from GetParent(), which can
        # behave inconsistently depending on a window's OS-level owner/
        # parent relationship. This matters specifically for
        # CustomStrategyDialog, which calls .transient(parent) -- that
        # changes the window's owner relationship in a way GetParent()
        # doesn't reliably follow, which is the most likely reason the
        # main window's title bar went dark but the dialog's didn't.
        GA_ROOT = 2
        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), GA_ROOT)
        value = ctypes.c_int(1)
        # Attribute ID is 20 on current Windows 10/11 builds, 19 on some
        # older Windows 10 builds -- try both, since there's no reliable
        # way to detect the exact build from here.
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
            if result == 0:  # S_OK
                break
    except Exception:
        pass


def main() -> None:
    theme_name = gui_theme.create_and_register_theme()
    root = ttk.Window(themename=theme_name)
    _apply_windows_dark_titlebar(root)

    # Defensive: explicitly force these colors from gui_theme.py's hex
    # constants directly, rather than relying solely on the custom theme
    # registration having succeeded (it can silently fall back to a
    # built-in theme with different colors -- see
    # gui_theme.create_and_register_theme()'s docstring). This guarantees
    # the window background and the Quick Run button match the chart's
    # colors exactly, pixel for pixel, regardless of that outcome.
    root.configure(background=gui_theme.CHART_BG)
    style = ttk.Style()
    for style_name in ("TFrame", "TLabel"):
        style.configure(style_name, background=gui_theme.CHART_BG, foreground=gui_theme.TEXT_CREAM)

    # Same reasoning, extended to input widgets: TEntry/TCombobox were
    # previously left entirely dependent on the custom theme registration
    # succeeding, unlike TFrame/TLabel above. If that registration falls
    # back (see gui_theme.create_and_register_theme()), these would
    # render in the FALLBACK theme's own colors instead of ours -- which
    # is exactly what caused the custom strategy dialog's entry fields to
    # show unrelated black/blue coloring. Note the option name difference:
    # Entry/Combobox use "fieldbackground" for the actual input area, not
    # "background" (which affects the border/decoration instead).
    style.configure("TEntry", fieldbackground=gui_theme.BG_CARD, foreground=gui_theme.TEXT_CREAM,
                     insertcolor=gui_theme.TEXT_CREAM, bordercolor=gui_theme.ACCENT_PRIMARY)
    style.configure("TCombobox", fieldbackground=gui_theme.BG_CARD, foreground=gui_theme.TEXT_CREAM,
                     background=gui_theme.BG_CARD, arrowcolor=gui_theme.TEXT_CREAM,
                     bordercolor=gui_theme.ACCENT_PRIMARY)
    style.map("TCombobox", fieldbackground=[("readonly", gui_theme.BG_CARD)],
              foreground=[("readonly", gui_theme.TEXT_CREAM)])

    # Quick Run's color is deliberately the SAME gui_theme constant as the
    # chart's median line (ACCENT_MUTED) -- both reference gui_theme
    # directly instead of going through ttkbootstrap's "info" bootstyle,
    # so they're guaranteed to match rather than hoping "info" happens to
    # map to the same hex value.
    #
    # font IS baked into the style definition here, not set on the widget
    # instance. ttkbootstrap's bootstyle-processing layer raises
    # "_tkinter.TclError: unknown option -font" whenever font is set
    # directly on a bootstyle/custom-style widget -- both as a
    # constructor kwarg and via a later .configure() call. Setting font
    # as part of the STYLE (Style.configure(style_name, font=...)) goes
    # through a different, working code path -- the widget then just
    # references the style name with no font argument anywhere on the
    # widget itself.
    style.configure("Accent.TButton", background=gui_theme.ACCENT_MUTED,
                     foreground=gui_theme.BG_DARKEST, bordercolor=gui_theme.ACCENT_MUTED,
                     focuscolor=gui_theme.ACCENT_MUTED, font=("", 14))
    style.map("Accent.TButton",
              background=[("active", gui_theme.ACCENT_MUTED), ("pressed", gui_theme.ACCENT_MUTED)])

    # Primary.TButton replaces bootstyle="primary" entirely (not just the
    # font issue) -- fully explicit, same reasoning as every other custom
    # style here: guaranteed colors regardless of theme registration, and
    # sidesteps bootstyle's problematic option handling altogether rather
    # than mixing it with a custom font in any form.
    style.configure("Primary.TButton", background=gui_theme.ACCENT_PRIMARY,
                     foreground=gui_theme.TEXT_CREAM, bordercolor=gui_theme.ACCENT_PRIMARY,
                     focuscolor=gui_theme.ACCENT_PRIMARY, font=("", 14))
    style.map("Primary.TButton",
              background=[("active", gui_theme.ACCENT_PRIMARY), ("pressed", gui_theme.ACCENT_PRIMARY)])

    # Compare All: the specific #ff964f requested, same size/font as the
    # other two buttons above it (font baked into the style, same pattern
    # as everything else here -- never set directly on the widget).
    style.configure("Compare.TButton", background=gui_theme.COMPARE_BUTTON,
                     foreground=gui_theme.BG_DARKEST, bordercolor=gui_theme.COMPARE_BUTTON,
                     focuscolor=gui_theme.COMPARE_BUTTON, font=("", 14))
    style.map("Compare.TButton",
              background=[("active", gui_theme.COMPARE_BUTTON), ("pressed", gui_theme.COMPARE_BUTTON)])

    # "Switch to Graph" -- the specific #CCCCC4 requested, same
    # font-baked-into-style pattern as every other button here.
    style.configure("SwitchGraph.TButton", background=gui_theme.SWITCH_GRAPH_BUTTON,
                     foreground=gui_theme.BG_DARKEST, bordercolor=gui_theme.SWITCH_GRAPH_BUTTON,
                     focuscolor=gui_theme.SWITCH_GRAPH_BUTTON, font=("", 14))
    style.map("SwitchGraph.TButton",
              background=[("active", gui_theme.SWITCH_GRAPH_BUTTON), ("pressed", gui_theme.SWITCH_GRAPH_BUTTON)])

    # Same explicit-over-bootstyle approach for the custom strategy
    # dialog's OK/Cancel buttons: OK uses the SAME green as the chart's
    # rally segments (ACCENT_SUCCESS), Cancel uses the SAME red as the
    # chart's decline segments (ACCENT_DANGER) -- guaranteed to match the
    # chart exactly, rather than depending on bootstyle "success"/
    # "secondary" happening to resolve to the same colors.
    style.configure("Success.TButton", background=gui_theme.ACCENT_SUCCESS,
                     foreground=gui_theme.TEXT_CREAM, bordercolor=gui_theme.ACCENT_SUCCESS,
                     focuscolor=gui_theme.ACCENT_SUCCESS)
    style.map("Success.TButton",
              background=[("active", gui_theme.ACCENT_SUCCESS), ("pressed", gui_theme.ACCENT_SUCCESS)])
    style.configure("Danger.TButton", background=gui_theme.ACCENT_DANGER,
                     foreground=gui_theme.TEXT_CREAM, bordercolor=gui_theme.ACCENT_DANGER,
                     focuscolor=gui_theme.ACCENT_DANGER)
    style.map("Danger.TButton",
              background=[("active", gui_theme.ACCENT_DANGER), ("pressed", gui_theme.ACCENT_DANGER)])

    SimulatorApp(root)

    def on_close() -> None:
        # Known matplotlib+Tkinter gotcha: closing the window alone can
        # leave the process running in the terminal, because pyplot's
        # global figure-manager state (and sometimes a pending after()
        # callback from FigureCanvasTkAgg) can outlive root.destroy() if
        # figures aren't explicitly closed first. plt.close("all") clears
        # that state before quit()/destroy() tear down the Tk side.
        plt.close("all")

        # Custom strategies are session-only by design -- simpler than
        # building a delete/manage UI for a feature capped at 10 entries.
        # Deleting the save file here means every session starts fresh
        # with none saved. load_saved_strategies() at startup still
        # exists as a safety net in case this doesn't get a chance to run
        # (e.g. the process is killed rather than closed normally) --
        # best-effort, wrapped so a failure here never blocks shutdown.
        try:
            if SAVED_STRATEGIES_PATH.exists():
                SAVED_STRATEGIES_PATH.unlink()
        except Exception:
            pass

        root.quit()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    # Belt-and-suspenders: if anything still lingers after mainloop()
    # returns, force the interpreter to exit rather than leaving a
    # process behind that requires a new terminal to run again.
    sys.exit(0)


if __name__ == "__main__":
    main()
