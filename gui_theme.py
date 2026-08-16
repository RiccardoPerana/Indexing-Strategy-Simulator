"""
gui_theme.py

The custom dark color palette for the GUI, defined ONCE here and shared
by both the ttkbootstrap theme (Tkinter widgets) and the matplotlib
chart's dark-mode styling in dashboard.py -- so the window chrome and the
chart are guaranteed to use exactly the same colors, not two hand-tuned
approximations of each other.
"""

# --- User-specified base palette ---
BG_DARKEST = "#06162B"      # main window background
BG_CARD = "#0B2A4A"         # card/input backgrounds (one step lighter than bg)
ACCENT_PRIMARY = "#1D4D7A"  # primary accent -- buttons, borders, focus rings
ACCENT_MUTED = "#8FB3C7"    # light steel blue -- muted accent AND the chart's median line
TEXT_CREAM = "#F2E9D8"      # main text color

# --- Invented, complementary accents ---
# ttkbootstrap requires success/warning/danger roles that the 5 base
# colors don't cover. Kept muted/desaturated so they read as part of the
# same navy-and-cream family rather than clashing primary colors.
ACCENT_SUCCESS = "#3C7A5C"   # muted teal-green
ACCENT_WARNING = "#B8912E"   # soft amber
ACCENT_DANGER = "#A5443C"    # muted brick-red
ACCENT_LIGHT = "#35566E"     # lighter blue-gray tint, between BG_CARD and ACCENT_MUTED

THEME_NAME = "navydark"

CUSTOM_THEME_COLORS = {
    "primary": ACCENT_PRIMARY,
    "secondary": BG_CARD,
    "success": ACCENT_SUCCESS,
    "info": ACCENT_MUTED,
    "warning": ACCENT_WARNING,
    "danger": ACCENT_DANGER,
    "light": ACCENT_LIGHT,
    "dark": BG_DARKEST,
    "bg": BG_DARKEST,
    "fg": TEXT_CREAM,
    "selectbg": ACCENT_PRIMARY,
    "selectfg": TEXT_CREAM,
    "border": ACCENT_PRIMARY,
    "inputfg": TEXT_CREAM,
    "inputbg": BG_CARD,
}

# --- Output panel value colors (return figures only) ---
# Deliberately soft/pastel rather than the chart's more saturated
# success/danger accents: results here skew positive (the whole point of
# the median-first, +3%/year-biased simulation setup), so strongly
# negative-implying red would rarely appear and green would otherwise
# dominate every panel -- muted colors read as informative without
# shouting on every run.
OUTPUT_POSITIVE = "#C1E1C1"
OUTPUT_NEGATIVE = "#FAA0A0"
# Median line stays the requested light blue; decline/rally reuse the
# same danger/success accents as the rest of the UI (one fewer color to
# keep track of, and it visually ties the chart to the app's own palette)
# rather than inventing yet another red/green pair.
CHART_BG = BG_DARKEST
CHART_CARD_BG = BG_CARD
CHART_TEXT = TEXT_CREAM
CHART_GRID = ACCENT_PRIMARY
CHART_MEDIAN_LINE = ACCENT_MUTED
CHART_DECLINE = ACCENT_DANGER
CHART_RALLY = ACCENT_SUCCESS
CHART_SAMPLE_RUNS = "#7C8B99"  # muted gray-blue for background individual runs, as requested

# --- "Compare All" feature colors ---
COMPARE_BUTTON = "#ff964f"
SWITCH_GRAPH_BUTTON = "#CCCCC4"

# Rank highlighting: green shades for top performers, red shades for
# bottom performers, most saturated at the extremes (best of best, worst
# of worst), fading toward neutral going inward.
RANK_GREEN_1ST = "#91CA91"  # best
RANK_GREEN_2ND = "#B0D9B0"
RANK_GREEN_3RD = "#C1E1C1"
RANK_RED_3RD_LAST = "#FBBBBB"
RANK_RED_2ND_LAST = "#FAA0A0"
RANK_RED_LAST = "#F76464"   # worst


def get_rank_color(rank: int, total: int) -> "str | None":
    """
    Returns the highlight color for a 0-indexed rank (0 = best) out of
    `total` items, or None if this rank isn't in the top-3/bottom-3.
    Top-3 checks come first, so with fewer than 6 items (where top-3 and
    bottom-3 ranges can overlap) a rank gets its TOP color, not both.
    """
    if rank == 0:
        return RANK_GREEN_1ST
    if rank == 1:
        return RANK_GREEN_2ND
    if rank == 2:
        return RANK_GREEN_3RD
    if rank == total - 1:
        return RANK_RED_LAST
    if rank == total - 2:
        return RANK_RED_2ND_LAST
    if rank == total - 3:
        return RANK_RED_3RD_LAST
    return None


def create_and_register_theme() -> str:
    """
    Registers the custom "navydark" theme with ttkbootstrap and returns
    its name, ready to pass to ttk.Window(themename=...).

    NOTE: ttkbootstrap's API for registering a custom theme
    (Style.register_theme + ThemeDefinition, used below) has changed
    across versions. If registration fails for any reason (version
    mismatch, changed API), this falls back to "darkly", the closest
    built-in dark theme, rather than crashing the app outright. If the
    app runs in ttkbootstrap's default dark theme instead of the custom
    navy/cream palette defined above, that fallback is why -- check the
    installed ttkbootstrap version against the register_theme call below.
    """
    try:
        from ttkbootstrap.style import Style, ThemeDefinition
        Style.register_theme(
            ThemeDefinition(name=THEME_NAME, themetype="dark", colors=CUSTOM_THEME_COLORS)
        )
        return THEME_NAME
    except Exception:
        return "darkly"
