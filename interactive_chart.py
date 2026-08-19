"""
interactive_chart.py

Adds "click-and-drag to pan, scroll wheel to zoom" behavior directly on a
matplotlib Axes -- no need to click a toolbar button first, unlike
matplotlib's default Pan/Zoom tools. This is what people generally expect
from an interactive chart (Google Maps-style navigation).

Every viewport calculation here is scale-aware: it runs in the axis's
LINEARIZED space, so pan/zoom/axis-drag behave identically and correctly
whether the chart is on a linear or a logarithmic y-scale (the GUI lets
the user toggle between the two at any time). See _axis_transforms.
"""

import math

# Imported for the "matplotlib.figure.Figure" / "matplotlib.axes.Axes"
# annotations on enable_hover_tooltip and enable_pan_and_scroll_zoom
# below. Those annotations are STRING literals, so Python itself never
# evaluates them and the module runs fine without these imports -- but a
# type checker does resolve them, and reports "matplotlib is not
# defined" if they're absent. Not unused: keep them.
import matplotlib.figure
import matplotlib.axes


def _axis_transforms(scale: str) -> tuple:
    """
    Returns (forward, inverse): functions mapping between DATA space and
    the axis's LINEARIZED space -- the space in which screen pixels are
    evenly spaced. Identity for a linear axis; log10 / 10**x for a log
    axis.

    WHY EVERY VIEWPORT CALCULATION MUST GO THROUGH THIS: on a log axis,
    a pixel is a constant step in log10(value), NOT in value. Doing pan
    and zoom arithmetic directly on data-space limits therefore produces
    two visible bugs: the gesture speeds up or slows down depending on
    where you are on the axis, and -- much worse -- panning downward can
    drive the lower limit to zero or negative, which is unrepresentable
    on a log scale. Matplotlib then warns and silently clamps the view.
    That second failure directly undoes the positive-lower-bound
    guarantee dashboard._draw_chart goes out of its way to establish for
    log mode.

    The forward transform floors its input at a tiny positive number
    rather than raising on a non-positive value. Matplotlib should never
    hand us a non-positive limit on a log axis, but a domain error
    raised inside a mouse-motion callback would be swallowed by the
    event loop and leave the chart mysteriously frozen -- clamping fails
    visibly and harmlessly instead.
    """
    if scale == "log":
        return (lambda v: math.log10(max(v, 1e-12))), (lambda v: 10.0 ** v)
    return (lambda v: v), (lambda v: v)


def _shift_limits(cur_lim, pixel_delta: float, axis_length_pixels: float,
                   scale: str = "linear") -> tuple:
    """
    Pure function: pan ONE axis by a pixel delta, correctly for a linear
    OR a log scale.

    Works by converting the pixel delta into a fraction of the axis's
    currently visible length, applying that fraction in LINEARIZED space
    (see _axis_transforms), then converting back. Because the shift is
    computed as a fraction of the CURRENT view rather than accumulated
    from where the drag started, this stays drift-free as the view moves
    underneath the cursor.
    """
    if axis_length_pixels == 0:
        return tuple(cur_lim)
    fwd, inv = _axis_transforms(scale)
    lo, hi = fwd(cur_lim[0]), fwd(cur_lim[1])
    delta = (pixel_delta / axis_length_pixels) * (hi - lo)
    return inv(lo - delta), inv(hi - delta)


def _compute_zoomed_limits(cur_xlim, cur_ylim, xdata, ydata, scale_factor):
    """
    Pure zoom calculation, factored out so it can be unit-tested without
    needing a live GUI event loop. Keeps the point (xdata, ydata) fixed in
    place while scaling the view by `scale_factor` (>1 = zoom out, <1 =
    zoom in).

    SCALE-AGNOSTIC BY CONTRACT: this does plain linear arithmetic and
    knows nothing about log axes. Callers are responsible for passing
    limits and the anchor point ALREADY in linearized space (via
    _axis_transforms) and for converting the result back. Keeping the
    transform out here leaves this a trivially testable pure function.
    """
    new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
    new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

    relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
    rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])

    new_xlim = (xdata - new_width * (1 - relx), xdata + new_width * relx)
    new_ylim = (ydata - new_height * (1 - rely), ydata + new_height * rely)
    return new_xlim, new_ylim


def _get_axis_region(ax, x_px, y_px, margin=35):
    """
    Determine whether a pixel position falls within the tick-label strip
    below the axes (the x-axis) or to the left of the axes (the y-axis),
    as opposed to inside the main plot area. Returns "x", "y", or None.

    Requires the figure to have been drawn at least once (ax.get_window_extent()
    needs a real renderer) -- true for any already-visible chart.
    """
    if x_px is None or y_px is None:
        return None
    bbox = ax.get_window_extent()
    # matplotlib pixel y-origin is bottom-left, so "below the axes" (where
    # the x-axis tick labels live) means a smaller y-pixel value than bbox.y0
    if bbox.y0 - margin <= y_px < bbox.y0 and bbox.x0 <= x_px <= bbox.x1:
        return "x"
    if bbox.x0 - margin <= x_px < bbox.x0 and bbox.y0 <= y_px <= bbox.y1:
        return "y"
    return None


def _compute_axis_drag_rescale(cur_lim, drag_pixels, axis_length_pixels,
                                sensitivity=2.5, scale: str = "linear"):
    """
    Pure function: given one axis's current (lo, hi) limits in DATA space,
    how many pixels the user has dragged along that axis since the last
    frame, and the axis's on-screen length in pixels, return the new
    (lo, hi) limits in data space.

    Convention: dragging toward LARGER matplotlib pixel values narrows the
    range -- increases the space between units, i.e. zooms in on that
    axis. Dragging the other way widens it. Note that matplotlib's pixel
    origin is BOTTOM-left, so "larger pixel value" means dragging RIGHT
    on the x-axis and dragging UP on the y-axis. (A previous version of
    this docstring said "down" for the y-axis, contradicting both the
    code here and the caller's own comment -- the code was and remains
    correct; the docstring was wrong.)

    Rescaling is anchored to the CENTER of the current view, not the
    cursor position -- unlike scroll-wheel zoom (which anchors to the
    cursor), axis-drag rescaling conventionally keeps the view centered
    while stretching/compressing it.

    `scale` is the axis's matplotlib scale ("linear" or "log"). All the
    arithmetic below happens in linearized space so that a log y-axis
    rescales evenly and can never be driven to a non-positive lower
    bound -- see _axis_transforms.
    """
    if axis_length_pixels == 0:
        return tuple(cur_lim)
    fwd, inv = _axis_transforms(scale)
    lo, hi = fwd(cur_lim[0]), fwd(cur_lim[1])
    width = hi - lo
    center = (lo + hi) / 2
    frac = (drag_pixels / axis_length_pixels) * sensitivity
    scale_factor = max(0.05, 1 - frac)  # floor prevents inverting/collapsing the range
    new_width = width * scale_factor
    return (inv(center - new_width / 2), inv(center + new_width / 2))


def _compute_annotation_offset(x_frac: float, y_frac: float, distance: float) -> tuple:
    """
    Pure function: given a point's fractional position within the axes'
    plot area (0.0 = left/bottom edge, 1.0 = right/top edge, in PIXEL
    space so this works correctly for a log-scale axis too, unlike a
    naive linear interpolation of data values) and a desired offset
    distance in points, return the (dx, dy) pixel offset to use for
    ax.annotate()'s xytext.

    Flips direction away from whichever edge the point is closer to, so
    the annotation box stays on-screen instead of running off the edge
    of the chart -- most noticeable on the RIGHT edge, which is also
    where the most recent (often most-watched) data sits, since these
    charts run left to right across time.
    """
    dx = -distance if x_frac > 0.5 else distance
    dy = -distance if y_frac > 0.5 else distance
    return dx, dy


def _find_nearest_index(x_values: list, x_query: float) -> int:
    """
    Pure lookup, factored out so it can be unit-tested without a live GUI
    event loop. Returns the index into x_values whose value is closest to
    x_query. Linear scan rather than binary search -- x_values here is a
    few hundred points at most (months in a 50-year run), so the
    difference is not measurable, and a linear scan doesn't require
    x_values to be sorted (binary search would).
    """
    best_i = 0
    best_dist = abs(x_values[0] - x_query)
    for i, x in enumerate(x_values):
        dist = abs(x - x_query)
        if dist < best_dist:
            best_dist = dist
            best_i = i
    return best_i


def enable_hover_tooltip(fig: "matplotlib.figure.Figure", ax: "matplotlib.axes.Axes",
                          x_values: list, y_values: list,
                          x_label: str = "Year", y_format: str = "\u20ac{:,.2f}",
                          bg_color: str = "white", text_color: str = "black",
                          distance: float = 18) -> None:
    """
    Shows a small floating tag that follows the highlighted point on the
    chart at a fixed pixel distance, with a marker dot placed exactly on
    that point -- e.g. hovering near year 23 shows "Year 23.4  €187.32"
    near a small circle sitting on the median line at that point, both
    updating live as the mouse moves.

    x_values/y_values must be the same length and index-aligned (e.g. the
    chart's years-axis and its median price line) -- the tag reports
    whichever (x_values[i], y_values[i]) pair has x_values[i] closest to
    the cursor's data-space x position. Deliberately reports only ONE
    line's value (the primary/median line the caller passes in), not
    every line on the chart -- consistent with median being the
    headline number throughout this project rather than cluttering the
    tag with the individual sample runs too.

    The tag is offset from the point by a FIXED DISTANCE in points (not
    data units), via matplotlib's own textcoords="offset points" -- this
    keeps the offset a constant on-screen size regardless of zoom level
    or whether the y-axis is linear or log. The offset DIRECTION flips
    based on which half of the CURRENT VIEW (in pixel space, via
    _compute_annotation_offset) the point sits in, so the tag always
    points away from the nearest edge -- otherwise a tag offset in one
    fixed direction gets clipped exactly when hovering near that edge,
    which is the most likely place to hover (e.g. checking the final
    year's value, right at the right edge of the chart).

    Hidden when the cursor leaves the axes, and suppressed while a
    button is held (event.button is not None during an active pan or
    axis-drag gesture from enable_pan_and_scroll_zoom) so neither the
    tag nor the marker update mid-drag.
    """
    if not x_values:
        return

    marker, = ax.plot([], [], marker="o", markersize=7, color=bg_color,
                       markeredgecolor=text_color, markeredgewidth=0.8,
                       linestyle="none", zorder=6)
    marker.set_visible(False)

    annotation = ax.annotate(
        "", xy=(0, 0), xytext=(distance, distance), textcoords="offset points",
        fontsize=9, zorder=10,
        bbox=dict(boxstyle="round,pad=0.35", facecolor=bg_color, edgecolor=bg_color, alpha=0.85),
        color=text_color,
    )
    annotation.set_visible(False)

    def hide_all():
        if annotation.get_visible() or marker.get_visible():
            annotation.set_visible(False)
            marker.set_visible(False)
            fig.canvas.draw_idle()

    def on_move(event):
        if event.inaxes != ax or event.xdata is None or event.button is not None:
            hide_all()
            return

        idx = _find_nearest_index(x_values, event.xdata)
        x_point, y_point = x_values[idx], y_values[idx]

        # Pixel-space position within the axes, so the edge-avoidance
        # logic is correct regardless of linear/log y-scale.
        px, py = ax.transData.transform((x_point, y_point))
        bbox = ax.get_window_extent()
        x_frac = (px - bbox.x0) / bbox.width
        y_frac = (py - bbox.y0) / bbox.height
        dx, dy = _compute_annotation_offset(x_frac, y_frac, distance)

        annotation.xy = (x_point, y_point)
        annotation.set_position((dx, dy))
        annotation.set_ha("right" if dx < 0 else "left")
        annotation.set_va("top" if dy < 0 else "bottom")
        annotation.set_text(f"{x_label} {x_point:.1f}   {y_format.format(y_point)}")
        annotation.set_visible(True)

        marker.set_data([x_point], [y_point])
        marker.set_visible(True)

        fig.canvas.draw_idle()

    def on_leave(event):
        hide_all()

    fig.canvas.mpl_connect("motion_notify_event", on_move)
    fig.canvas.mpl_connect("axes_leave_event", on_leave)


def enable_pan_and_scroll_zoom(fig: "matplotlib.figure.Figure",
                                ax: "matplotlib.axes.Axes",
                                zoom_scale: float = 1.15) -> None:
    """
    Wire up pan-by-drag and zoom-by-scroll on a single Axes.

    Args:
        fig: the Figure that owns the canvas to listen on.
        ax: the Axes to make interactive. Only this Axes reacts --
            e.g. a stats text panel elsewhere in the same figure is
            unaffected.
        zoom_scale: how much each scroll "click" zooms in/out (1.15 =
            15% per notch). Larger = faster zoom.

    Also enables click-and-drag directly on the x-axis or y-axis tick-label
    strip (below/left of the plot area) to stretch or compress that axis's
    scale independently -- distinct from dragging inside the plot area,
    which pans both axes together instead.
    """
    state = {"mode": None, "last_x": None, "last_y": None}  # mode: None, "pan", "axis_x", or "axis_y"

    def on_scroll(event):
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return
        # scroll up ("up") = zoom in, scroll down ("down") = zoom out
        scale_factor = (1 / zoom_scale) if event.button == "up" else zoom_scale

        # Convert both axes into linearized space, zoom there, convert
        # back. The x-axis is always linear on these charts (years), but
        # it's read from the Axes rather than assumed -- one code path
        # that stays correct if that ever changes.
        x_fwd, x_inv = _axis_transforms(ax.get_xscale())
        y_fwd, y_inv = _axis_transforms(ax.get_yscale())

        cur_xlim = (x_fwd(ax.get_xlim()[0]), x_fwd(ax.get_xlim()[1]))
        cur_ylim = (y_fwd(ax.get_ylim()[0]), y_fwd(ax.get_ylim()[1]))

        new_xlim, new_ylim = _compute_zoomed_limits(
            cur_xlim, cur_ylim, x_fwd(event.xdata), y_fwd(event.ydata), scale_factor)

        ax.set_xlim(x_inv(new_xlim[0]), x_inv(new_xlim[1]))
        ax.set_ylim(y_inv(new_ylim[0]), y_inv(new_ylim[1]))
        fig.canvas.draw_idle()

    def on_press(event):
        if event.button != 1:  # left mouse button only
            return
        if event.inaxes == ax:
            state["mode"] = "pan"
        else:
            axis_region = _get_axis_region(ax, event.x, event.y)
            if axis_region == "x":
                state["mode"] = "axis_x"
            elif axis_region == "y":
                state["mode"] = "axis_y"
            else:
                return  # click was outside both the plot and any axis strip
        state["last_x"] = event.x  # pixel coordinates, not data coordinates
        state["last_y"] = event.y

    def on_motion(event):
        if state["mode"] is None or event.x is None or event.y is None:
            return

        if state["mode"] == "pan":
            # Shift each axis by the drag delta expressed as a fraction of
            # that axis's currently visible span, computed in LINEARIZED
            # space (see _shift_limits / _axis_transforms). Recomputing
            # from the current limits every frame -- rather than diffing
            # against where the drag started -- avoids drift/runaway
            # panning as the view itself moves.
            #
            # This replaces an earlier implementation that inverted
            # ax.transData to get a data-space delta and subtracted it
            # from the limits directly. That is correct on a linear axis
            # but wrong on a log one: a constant data-space delta is not
            # a constant pixel distance there, so panning felt uneven
            # and, dragging downward far enough, pushed the lower limit
            # to <= 0 -- unrepresentable on a log scale, which matplotlib
            # answers with a warning and a silently clamped view.
            bbox = ax.get_window_extent()
            ax.set_xlim(_shift_limits(ax.get_xlim(), event.x - state["last_x"],
                                       bbox.width, ax.get_xscale()))
            ax.set_ylim(_shift_limits(ax.get_ylim(), event.y - state["last_y"],
                                       bbox.height, ax.get_yscale()))

        elif state["mode"] == "axis_x":
            bbox = ax.get_window_extent()
            drag_px = event.x - state["last_x"]
            new_xlim = _compute_axis_drag_rescale(ax.get_xlim(), drag_px, bbox.width,
                                                   scale=ax.get_xscale())
            ax.set_xlim(new_xlim)

        elif state["mode"] == "axis_y":
            bbox = ax.get_window_extent()
            # Same sign convention as the x-axis case, verified directly
            # against matplotlib's actual pixel coordinate system (bottom-
            # left origin, y increases UPWARD -- confirmed by inspection,
            # not assumed): a positive pixel delta (dragging up) narrows
            # the range and zooms in; dragging down widens it. This makes
            # "drag toward increasing axis value" the consistent zoom-in
            # gesture for both axes. (_compute_axis_drag_rescale's
            # docstring previously described the opposite direction for
            # the y-axis; the docstring has been corrected to match this.)
            drag_px = event.y - state["last_y"]
            new_ylim = _compute_axis_drag_rescale(ax.get_ylim(), drag_px, bbox.height,
                                                   scale=ax.get_yscale())
            ax.set_ylim(new_ylim)

        state["last_x"] = event.x
        state["last_y"] = event.y
        fig.canvas.draw_idle()

    def on_release(event):
        state["mode"] = None

    fig.canvas.mpl_connect("scroll_event", on_scroll)
    fig.canvas.mpl_connect("button_press_event", on_press)
    fig.canvas.mpl_connect("motion_notify_event", on_motion)
    fig.canvas.mpl_connect("button_release_event", on_release)
