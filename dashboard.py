"""
dashboard.py

Chart-drawing and stats-formatting utilities used by the desktop GUI
(gui_tk.py). Builds matplotlib Figures for embedding in a Tkinter canvas
and structures backtest stats for display in real widgets, rather than
producing any output directly itself.
"""

import matplotlib.pyplot as plt
from backtest import BacktestResult
from interactive_chart import enable_pan_and_scroll_zoom


def summary_groups(result: BacktestResult) -> list:
    """
    Backtest stats as grouped (label, value, raw) triples, for UIs that
    lay out real label/value widgets (e.g. ttk Labels in a grid) rather
    than relying on monospace alignment. Returns a list of (group_title,
    [(label, value, raw), ...]) tuples, each group getting its own
    separator and header.

    "Runs simulated" is omitted entirely (redundant with the "Number of
    runs" field already visible in the settings panel), and Avg return is
    dropped (median return + median annualized return cover the "typical
    outcome" story on their own).

    `raw` is the underlying signed numeric value (already in percent
    units, e.g. 5.0 for +5%, matching what's shown in the formatted
    string) for return figures where positive/negative has real meaning
    -- letting a UI color-code by actual sign rather than parsing the
    formatted string back into a number. It's None for figures where sign
    isn't a meaningful gain/loss indicator (counts, prices, portfolio
    values). For the IQR row specifically, `raw` is a (low, high) tuple --
    the cell shows two numbers ("-31.0% to 139.2%") that a UI may want to
    style differently (e.g. the low/worse end always in the same color
    used for negative values, the high/better end always in the color
    used for positive values, by position rather than each number's own
    sign) rather than treating the whole cell as one value.
    """
    s = result.summary()
    return [
        ("Return", [
            ("Median return", f"{s['median_return_pct']:.2f}%", s['median_return_pct']),
            ("Median annualized return", f"{s['median_annual_return_pct']:.2f}%", s['median_annual_return_pct']),
            ("Typical range (IQR)", f"{s['iqr_return_low_pct']:.1f}% to {s['iqr_return_high_pct']:.1f}%",
             (s['iqr_return_low_pct'], s['iqr_return_high_pct'])),
        ]),
        ("Portfolio", [
            ("Median cash invested", f"\u20ac{s['median_cash_invested']:,.0f}", None),
            ("Median ending value", f"\u20ac{s['median_ending_portfolio_value']:,.0f}", None),
        ]),
        ("Price", [
            ("Starting price", f"\u20ac{s['starting_price']:,.2f}", None),
            ("Median ending price", f"\u20ac{s['median_ending_price']:,.2f}", None),
        ]),
    ]


def _find_sustained_trends(prices: list, reversal_threshold: float = 0.10,
                            rally_annual_rate: float = 0.05,
                            decline_annual_rate: float = -0.04,
                            max_segment_years: float = 5.0) -> tuple:
    """
    Identify sustained rallies/declines that are both (a) confirmed swings
    via a zigzag/peak-trough algorithm, AND (b) moving unusually fast on
    an annualized basis -- not just "eventually moved a lot."

    STRUCTURAL ISSUE THIS FIXES: a plain zigzag algorithm has no "calm"
    state -- it partitions the ENTIRE timeline into alternating up/down
    segments by construction, so it always covers ~100% of the chart no
    matter what reversal_threshold is set to (verified directly -- lowering
    the threshold only created more, smaller segments, never gaps). With
    low volatility and a steady positive drift, that meant almost the
    whole 50-year chart routinely became one giant "rally" -- technically
    true (price never pulled back 20%) but useless as a highlight.

    The fix: after finding zigzag pivots, each segment is also required to
    clear an annualized rate bar -- a rally must compound at least
    `rally_annual_rate`/year, a decline must fall at least
    `decline_annual_rate`/year -- computed via (end/start)**(1/years)-1,
    the same proper compounding used elsewhere in this project (not a
    naive average). Segments that don't clear the bar are simply left
    uncolored, which is what actually distinguishes "this was a genuine
    multi-year bull/bear run" from "the market gently drifted up like it
    usually does." This annualized-rate check is itself a momentum
    indicator (a Rate-of-Change filter) -- it's not a separate concept
    from "using momentum," it just wasn't labeled that explicitly before.

    SECOND ISSUE, FOUND LATER: the rate bar is an ABSOLUTE threshold, not
    relative to any individual run. Since each run samples its own random
    drift, some runs land on an unusually strong (or weak) drift for
    their ENTIRE 50-year duration -- and if a run's whole trajectory
    legitimately compounds above the rate bar the whole time, nothing
    stopped that from being reported as one continuous, chart-spanning
    segment. Confirmed empirically: scanning 100 seeds found 10 with
    >60% chart coverage, some reaching 100%, with individual segments
    running 11-22 years. Fixed with `max_segment_years`: any segment
    (even one that legitimately clears the rate bar) longer than this is
    simply dropped rather than drawn -- an "entire multi-decade span"
    isn't really a discrete, notable event to highlight anymore anyway.
    Verified this eliminates the problem: re-scanning the same 100 seeds
    with max_segment_years=5, ZERO showed >60% coverage (max observed
    51%, down from 100%), while the typical/desired case was essentially
    unaffected (median duration 1.6yr both before and after, since the
    cap only ever discards the rare outlier, not the normal ~1.5-2yr
    segments this was already tuned to produce).

    IMPORTANT: chart-only. No connection to market_events.py or the
    Strategy engine -- it cannot influence what any strategy buys, only
    what gets drawn.

    Returns (decline_segments, rally_segments), each a list of
    (month_index_start, month_index_end) tuples.

    CALIBRATION NOTE -- READ BEFORE CHANGING: this MUST be calibrated
    against result.median_price_by_month() (the actual median-of-many-runs
    series the chart plots), NOT a single raw price path. An earlier
    version of these bars (0.12 / -0.08) was calibrated against raw single
    runs, where events are much larger, and then silently produced ZERO
    events on every real backtest once actually measured against the
    median series -- median-of-many-runs is a cross-sectional statistic,
    not a real trajectory, and it's meaningfully smoother than any
    individual run because each run's sharp moves happen at different
    times and get averaged out. Current values (reversal=0.10,
    rally>=5%/yr, decline<=-4%/yr, max_segment_years=5) were verified
    directly against run_backtest(...).median_price_by_month() across
    100 seeds. If price_generator's volatility/drift changes, or
    num_runs changes materially, re-verify against the REAL pathway, not
    a shortcut.
    """
    n = len(prices)
    if n < 2:
        return [], []

    max_segment_months = max_segment_years * 12

    def annualized_rate(i0: int, i1: int) -> float:
        years = (i1 - i0) / 12
        if years <= 0 or prices[i0] <= 0:
            return 0.0
        return (prices[i1] / prices[i0]) ** (1 / years) - 1

    decline_segments, rally_segments = [], []
    pivot_idx = 0                      # last confirmed swing point
    max_idx, max_price = 0, prices[0]  # running high since pivot
    min_idx, min_price = 0, prices[0]  # running low since pivot
    trend = None                       # None, "up", or "down"

    for i in range(1, n):
        price = prices[i]
        if price > max_price:
            max_price, max_idx = price, i
        if price < min_price:
            min_price, min_idx = price, i

        if trend != "down" and max_price > 0 and (price - max_price) / max_price <= -reversal_threshold:
            if (trend == "up" and annualized_rate(pivot_idx, max_idx) >= rally_annual_rate
                    and (max_idx - pivot_idx) <= max_segment_months):
                rally_segments.append((pivot_idx, max_idx))
            pivot_idx = max_idx
            trend = "down"
            min_idx, min_price = i, price
            continue

        if trend != "up" and min_price > 0 and (price - min_price) / min_price >= reversal_threshold:
            if (trend == "down" and annualized_rate(pivot_idx, min_idx) <= decline_annual_rate
                    and (min_idx - pivot_idx) <= max_segment_months):
                decline_segments.append((pivot_idx, min_idx))
            pivot_idx = min_idx
            trend = "up"
            max_idx, max_price = i, price
            continue

    # close out whatever trend is still running at the end of the series
    if (trend == "up" and max_idx > pivot_idx and annualized_rate(pivot_idx, max_idx) >= rally_annual_rate
            and (max_idx - pivot_idx) <= max_segment_months):
        rally_segments.append((pivot_idx, max_idx))
    elif (trend == "down" and min_idx > pivot_idx and annualized_rate(pivot_idx, min_idx) <= decline_annual_rate
            and (min_idx - pivot_idx) <= max_segment_months):
        decline_segments.append((pivot_idx, min_idx))

    return decline_segments, rally_segments


def _draw_chart(ax_chart, result: BacktestResult, strategy_name: str,
                 num_sample_runs: int = 5, dark_mode: bool = False,
                 y_scale: str = "linear") -> None:
    """
    Draw the price chart (individual runs + median + sustained trends) onto
    an existing Axes.

    dark_mode=True pulls the palette from gui_theme.py, so the chart and
    the ttkbootstrap window chrome are guaranteed to match exactly.

    y_scale: "linear" (default) or "log". Matplotlib's log scale requires
    a strictly positive lower axis bound -- unlike the linear case, which
    can floor at 0.0, the log branch below must never let the lower bound
    reach zero or matplotlib will raise.
    """
    if dark_mode:
        import gui_theme
        sample_color = gui_theme.CHART_SAMPLE_RUNS
        median_color = gui_theme.CHART_MEDIAN_LINE
        decline_color = gui_theme.CHART_DECLINE
        rally_color = gui_theme.CHART_RALLY
    else:
        sample_color = "#c0c0c0"
        median_color = "#2563eb"
        decline_color = "#dc2626"
        rally_color = "#16a34a"

    median_prices = result.median_price_by_month()
    months = list(range(len(median_prices)))
    years_axis = [m / 12 for m in months]  # x-axis in years, not months

    # Background: a handful of individual runs in thin light gray, so the
    # median line can be read in context of how much runs actually vary
    # (some crash hard, some boom -- the median alone hides that spread).
    sample_count = min(num_sample_runs, len(result.price_series_used))
    for i, series in enumerate(result.price_series_used[:sample_count]):
        ax_chart.plot(years_axis, series, color=sample_color, linewidth=0.6,
                       alpha=0.7, zorder=1,
                       label="Sample runs" if i == 0 else None)

    # Median: bold and on top -- the "typical run" line. The average is
    # intentionally NOT drawn on the chart at all (it's still shown as a
    # number in the stats panel) -- plotting it invites reading the chart
    # as "the average", which is exactly the skewed framing we're avoiding.
    ax_chart.plot(years_axis, median_prices, color=median_color, linewidth=1.8,
                   zorder=3, label="Median")

    # Highlight SUSTAINED trends (rallies/declines of any duration -- could
    # be a few months or many years) the same way -- tracing the actual
    # median-line path over the whole trend in red/green.
    decline_segments, rally_segments = _find_sustained_trends(median_prices)
    for idx, (i0, i1) in enumerate(decline_segments):
        xs = [m / 12 for m in range(i0, i1 + 1)]
        ys = median_prices[i0:i1 + 1]
        ax_chart.plot(xs, ys, color=decline_color, linewidth=1.8, zorder=4,
                       solid_capstyle="round",
                       label="Sustained decline" if idx == 0 else None)
    for idx, (i0, i1) in enumerate(rally_segments):
        xs = [m / 12 for m in range(i0, i1 + 1)]
        ys = median_prices[i0:i1 + 1]
        ax_chart.plot(xs, ys, color=rally_color, linewidth=1.8, zorder=4,
                       solid_capstyle="round",
                       label="Sustained rally" if idx == 0 else None)

    ax_chart.set_title(f"Median Index Price ({result.num_runs} runs)")
    ax_chart.set_xlabel("Year")
    ax_chart.set_ylabel("Price")
    ax_chart.grid(True, alpha=0.3)
    ax_chart.legend(loc="upper left", fontsize=9)

    # Size the y-axis to the MEDIAN line's own range, not whatever the
    # tallest individual sample run happens to reach. Without this, a
    # single outlier run in the gray background lines can stretch the
    # whole chart so far that the median line gets squashed flat near
    # the bottom -- exactly the outcome we're trying to avoid by leading
    # with median in the first place.
    median_min, median_max = min(median_prices), max(median_prices)
    price_span = median_max - median_min
    padding = price_span * 0.08 if price_span > 0 else max(median_max * 0.1, 1.0)

    if y_scale == "log":
        ax_chart.set_yscale("log")
        # A strictly positive lower bound is required for log scale --
        # the linear branch's max(0.0, ...) floor would be invalid here.
        lower = median_min - padding
        if lower <= 0:
            lower = max(median_min * 0.5, 0.01)
        ax_chart.set_ylim(lower, median_max + padding)
    else:
        ax_chart.set_ylim(max(0.0, median_min - padding), median_max + padding)

    if dark_mode:
        _apply_dark_chart_styling(ax_chart)


def _apply_dark_chart_styling(ax) -> None:
    """
    Recolors chart chrome (background, spines, ticks, labels, grid,
    legend) to match gui_theme.py's dark palette. Only touches styling,
    never data -- called after all data is plotted.

    Uses the SAME background color as the rest of the window (CHART_BG)
    and removes the axes border (spines) entirely, so the chart reads as
    integrated with the settings/output panels rather than a distinct
    floating card.
    """
    import gui_theme
    fig = ax.figure
    fig.patch.set_facecolor(gui_theme.CHART_BG)
    ax.set_facecolor(gui_theme.CHART_BG)  # matches the figure bg exactly -- no visible seam
    for spine in ax.spines.values():
        spine.set_visible(False)  # no border
    ax.tick_params(colors=gui_theme.CHART_TEXT)
    ax.xaxis.label.set_color(gui_theme.CHART_TEXT)
    ax.yaxis.label.set_color(gui_theme.CHART_TEXT)
    ax.title.set_color(gui_theme.CHART_TEXT)
    ax.grid(True, color=gui_theme.CHART_GRID, alpha=0.2)

    legend = ax.get_legend()
    if legend is not None:
        legend.get_frame().set_facecolor(gui_theme.CHART_BG)
        legend.get_frame().set_edgecolor(gui_theme.CHART_BG)  # no visible legend border either
        for text in legend.get_texts():
            text.set_color(gui_theme.CHART_TEXT)


def build_chart_figure(result: BacktestResult, strategy_name: str,
                        num_sample_runs: int = 5, figsize: tuple = (9.5, 6.0),
                        dark_mode: bool = False, y_scale: str = "linear"):
    """
    Build a standalone matplotlib Figure containing just the price chart,
    for embedding in a Tkinter canvas via FigureCanvasTkAgg.

    Use `summary_groups(result)` separately to get the stats for whatever
    native widget the GUI wants to show them in -- don't bake stats into
    this figure, since real widgets look sharper and are selectable/
    copyable, unlike text rendered inside a matplotlib Axes.

    Pan/scroll-zoom is wired up via enable_pan_and_scroll_zoom, which only
    relies on the generic matplotlib event system (fig.canvas.mpl_connect).

    dark_mode=True colors the chart to match gui_theme.py's palette (see
    _apply_dark_chart_styling).

    y_scale: "linear" (default) or "log" -- see _draw_chart's docstring
    for the log-scale positive-lower-bound handling.

    Returns the Figure -- caller is responsible for embedding it (this
    function never calls plt.show() or savefig()).
    """
    fig, ax_chart = plt.subplots(figsize=figsize)
    _draw_chart(ax_chart, result, strategy_name, num_sample_runs, dark_mode=dark_mode, y_scale=y_scale)
    fig.tight_layout()
    enable_pan_and_scroll_zoom(fig, ax_chart)
    return fig
