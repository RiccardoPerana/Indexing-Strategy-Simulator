/*
 * chart.js
 *
 * A small self-contained Canvas 2D price chart. Draws: a handful of
 * sample price runs (thin, muted), the bold median line, sustained
 * rally/decline highlight segments, and supports click-drag pan,
 * scroll-wheel zoom anchored at the cursor, and drag-on-the-axis-strip
 * to rescale a single axis independently.
 */

function axisTransforms(scale) {
  if (scale === "log") {
    return [(v) => Math.log10(Math.max(v, 1e-12)), (v) => Math.pow(10, v)];
  }
  return [(v) => v, (v) => v];
}

function shiftLimits(curLim, pixelDelta, axisLengthPixels, scale) {
  if (axisLengthPixels === 0) return curLim;
  const [fwd, inv] = axisTransforms(scale);
  const lo = fwd(curLim[0]), hi = fwd(curLim[1]);
  const delta = (pixelDelta / axisLengthPixels) * (hi - lo);
  return [inv(lo - delta), inv(hi - delta)];
}

function computeZoomedLimits(curXlim, curYlim, xdata, ydata, scaleFactor) {
  const newWidth = (curXlim[1] - curXlim[0]) * scaleFactor;
  const newHeight = (curYlim[1] - curYlim[0]) * scaleFactor;

  const relx = (curXlim[1] - xdata) / (curXlim[1] - curXlim[0]);
  const rely = (curYlim[1] - ydata) / (curYlim[1] - curYlim[0]);

  return [
    [xdata - newWidth * (1 - relx), xdata + newWidth * relx],
    [ydata - newHeight * (1 - rely), ydata + newHeight * rely],
  ];
}

function computeAxisDragRescale(curLim, dragPixels, axisLengthPixels, scale, sensitivity = 2.5) {
  if (axisLengthPixels === 0) return curLim;
  const [fwd, inv] = axisTransforms(scale);
  const lo = fwd(curLim[0]), hi = fwd(curLim[1]);
  const width = hi - lo;
  const center = (lo + hi) / 2;
  const frac = (dragPixels / axisLengthPixels) * sensitivity;
  const scaleFactor = Math.max(0.05, 1 - frac);
  const newWidth = width * scaleFactor;
  return [inv(center - newWidth / 2), inv(center + newWidth / 2)];
}

function findNearestIndex(xValues, xQuery) {
  let bestI = 0;
  let bestDist = Math.abs(xValues[0] - xQuery);
  for (let i = 1; i < xValues.length; i++) {
    const dist = Math.abs(xValues[i] - xQuery);
    if (dist < bestDist) { bestDist = dist; bestI = i; }
  }
  return bestI;
}

const CHART_PAD = { left: 64, right: 18, top: 46, bottom: 40 };
const AXIS_STRIP = 28; // pixel margin outside the plot area that counts as "drag this axis"

/**
 * Mounts an interactive price chart into `container` (any block element;
 * its contents are replaced). `data` = { sampleSeries, median,
 * declineSegments, rallySegments, numRuns, title }. `options.yScale` =
 * "linear" | "log".
 *
 * Returns a controller with setYScale(scale) to rebuild in place.
 */
function mountPriceChart(container, data, options = {}) {
  let yScale = options.yScale || "linear";
  const { sampleSeries, median: medianPrices, declineSegments, rallySegments, numRuns, title } = data;
  const yearsAxis = medianPrices.map((_, i) => i / 12);

  container.innerHTML = "";
  container.classList.add("chart-host");

  // The canvas lives inside an absolutely positioned "stage" that fills
  // the container but is taken out of normal flow. That breaks the
  // resize feedback loop: the container's size is decided purely by the
  // page layout, the canvas is sized to match it, and the canvas can
  // never push the container (and therefore itself) any bigger.
  const stage = document.createElement("div");
  stage.className = "chart-stage";
  container.appendChild(stage);
  const canvas = document.createElement("canvas");
  canvas.className = "chart-canvas";
  stage.appendChild(canvas);
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;
  stage.appendChild(tooltip);

  const ctx = canvas.getContext("2d");
  let dpr = window.devicePixelRatio || 1;
  let cssW = 0, cssH = 0;

  let view = null; // { xlim: [lo,hi], ylim: [lo,hi] } always in DATA space

  function fitView() {
    const medMin = Math.min(...medianPrices);
    const medMax = Math.max(...medianPrices);
    const span = medMax - medMin;
    const padding = span > 0 ? span * 0.08 : Math.max(medMax * 0.1, 1.0);

    let lower, upper;
    if (yScale === "log") {
      lower = medMin - padding;
      if (lower <= 0) lower = Math.max(medMin * 0.5, 0.01);
      upper = medMax + padding;
    } else {
      lower = Math.max(0.0, medMin - padding);
      upper = medMax + padding;
    }

    view = {
      xlim: [yearsAxis[0], yearsAxis[yearsAxis.length - 1]],
      ylim: [lower, upper],
    };
  }
  fitView();

  function plotRect() {
    return {
      x: CHART_PAD.left,
      y: CHART_PAD.top,
      w: Math.max(1, cssW - CHART_PAD.left - CHART_PAD.right),
      h: Math.max(1, cssH - CHART_PAD.top - CHART_PAD.bottom),
    };
  }

  function xToPx(x) {
    const r = plotRect();
    const [lo, hi] = view.xlim;
    return r.x + ((x - lo) / (hi - lo)) * r.w;
  }
  function pxToX(px) {
    const r = plotRect();
    const [lo, hi] = view.xlim;
    return lo + ((px - r.x) / r.w) * (hi - lo);
  }
  function yToPx(y) {
    const r = plotRect();
    const [fwd] = axisTransforms(yScale);
    const lo = fwd(view.ylim[0]), hi = fwd(view.ylim[1]);
    const yv = fwd(y);
    return r.y + (1 - (yv - lo) / (hi - lo)) * r.h;
  }
  function pxToY(py) {
    const r = plotRect();
    const [fwd, inv] = axisTransforms(yScale);
    const lo = fwd(view.ylim[0]), hi = fwd(view.ylim[1]);
    const t = 1 - (py - r.y) / r.h;
    return inv(lo + t * (hi - lo));
  }

  function niceTicks(lo, hi, count, log) {
    if (log) {
      const loE = Math.floor(Math.log10(Math.max(lo, 1e-12)));
      const hiE = Math.ceil(Math.log10(Math.max(hi, 1e-12)));
      const ticks = [];
      for (let e = loE; e <= hiE; e++) {
        for (const m of [1, 2, 5]) {
          const v = m * Math.pow(10, e);
          if (v >= lo * 0.999 && v <= hi * 1.001) ticks.push(v);
        }
      }
      return ticks.length ? ticks : [lo, hi];
    }
    const span = hi - lo;
    if (span <= 0) return [lo];
    const rough = span / count;
    const mag = Math.pow(10, Math.floor(Math.log10(rough)));
    const norm = rough / mag;
    let step;
    if (norm < 1.5) step = 1 * mag;
    else if (norm < 3) step = 2 * mag;
    else if (norm < 7) step = 5 * mag;
    else step = 10 * mag;
    const start = Math.ceil(lo / step) * step;
    const ticks = [];
    for (let v = start; v <= hi + step * 1e-6; v += step) ticks.push(v);
    return ticks;
  }

  function formatPrice(v) {
    if (v >= 1000) return "€" + Math.round(v).toLocaleString("en-US");
    return "€" + v.toFixed(v >= 100 ? 0 : 2);
  }

  function draw() {
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = Theme.CHART_BG;
    ctx.fillRect(0, 0, cssW, cssH);

    const r = plotRect();

    // gridlines + tick labels
    ctx.strokeStyle = Theme.CHART_GRID;
    ctx.globalAlpha = 0.28;
    ctx.lineWidth = 1;
    ctx.fillStyle = Theme.CHART_TEXT;
    ctx.font = "11px system-ui, sans-serif";

    const xTicks = niceTicks(view.xlim[0], view.xlim[1], Math.max(2, Math.floor(r.w / 70)), false);
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const t of xTicks) {
      const px = xToPx(t);
      if (px < r.x - 1 || px > r.x + r.w + 1) continue;
      ctx.globalAlpha = 0.28;
      ctx.beginPath();
      ctx.moveTo(px, r.y);
      ctx.lineTo(px, r.y + r.h);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(t.toFixed(t < 10 ? 1 : 0), px, r.y + r.h + 6);
    }

    const yTicks = niceTicks(view.ylim[0], view.ylim[1], Math.max(2, Math.floor(r.h / 45)), yScale === "log");
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const t of yTicks) {
      const py = yToPx(t);
      if (py < r.y - 1 || py > r.y + r.h + 1) continue;
      ctx.globalAlpha = 0.28;
      ctx.beginPath();
      ctx.moveTo(r.x, py);
      ctx.lineTo(r.x + r.w, py);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(formatPrice(t), r.x - 8, py);
    }

    // axis labels
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.fillText("Year", r.x + r.w / 2, cssH - 6);
    ctx.save();
    ctx.translate(14, r.y + r.h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Price", 0, 0);
    ctx.restore();

    // title
    ctx.textAlign = "left";
    ctx.font = "bold 13px system-ui, sans-serif";
    ctx.fillText(title || `Median Index Price (${numRuns} runs)`, r.x, 22);

    // plot series, clipped to the plot rect
    ctx.save();
    ctx.beginPath();
    ctx.rect(r.x, r.y, r.w, r.h);
    ctx.clip();

    function strokePath(series, color, width, alpha, dashed) {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.globalAlpha = alpha;
      ctx.lineCap = dashed ? "round" : "butt";
      let started = false;
      for (let i = 0; i < series.length; i++) {
        const v = series[i];
        if (yScale === "log" && v <= 0) continue;
        const px = xToPx(yearsAxis[i]);
        const py = yToPx(v);
        if (!started) { ctx.moveTo(px, py); started = true; } else { ctx.lineTo(px, py); }
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    const sampleCount = Math.min(5, sampleSeries.length);
    for (let i = 0; i < sampleCount; i++) {
      strokePath(sampleSeries[i], Theme.CHART_SAMPLE_RUNS, 0.9, 0.7, false);
    }

    strokePath(medianPrices, Theme.CHART_MEDIAN_LINE, 2.2, 1, false);

    function strokeSegment(seg, color) {
      const slice = [];
      for (let i = seg[0]; i <= seg[1]; i++) slice.push(medianPrices[i]);
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.4;
      ctx.lineCap = "round";
      let started = false;
      for (let i = 0; i < slice.length; i++) {
        const px = xToPx(yearsAxis[seg[0] + i]);
        const py = yToPx(slice[i]);
        if (!started) { ctx.moveTo(px, py); started = true; } else { ctx.lineTo(px, py); }
      }
      ctx.stroke();
    }
    for (const seg of declineSegments) strokeSegment(seg, Theme.CHART_DECLINE);
    for (const seg of rallySegments) strokeSegment(seg, Theme.CHART_RALLY);

    ctx.restore(); // clip

    // plot border
    ctx.strokeStyle = Theme.CHART_GRID;
    ctx.globalAlpha = 0.5;
    ctx.lineWidth = 1;
    ctx.strokeRect(r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1);
    ctx.globalAlpha = 1;

    // legend
    const legendItems = [
      ["Sample runs", Theme.CHART_SAMPLE_RUNS],
      ["Median", Theme.CHART_MEDIAN_LINE],
    ];
    if (declineSegments.length) legendItems.push(["Sustained decline", Theme.CHART_DECLINE]);
    if (rallySegments.length) legendItems.push(["Sustained rally", Theme.CHART_RALLY]);

    // Items wrap onto another row when the plot is too narrow to hold them
    // all on one (a phone), instead of running past its right edge.
    ctx.font = "11px system-ui, sans-serif";
    const legendLeft = r.x + 10, legendRight = r.x + r.w - 10;
    let lx = legendLeft, ly = r.y + 12;
    const lineW = 16, gap = 8, rowH = 16;
    for (const [label, color] of legendItems) {
      const itemW = lineW + 5 + ctx.measureText(label).width;
      if (lx > legendLeft && lx + itemW > legendRight) {
        lx = legendLeft;
        ly += rowH;
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.moveTo(lx, ly);
      ctx.lineTo(lx + lineW, ly);
      ctx.stroke();
      ctx.fillStyle = Theme.CHART_TEXT;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(label, lx + lineW + 5, ly);
      lx += itemW + gap + 10;
    }

    ctx.restore();
  }

  function resize() {
    const rect = stage.getBoundingClientRect();
    // Hidden containers (e.g. the single-run chart while Compare mode is
    // showing) measure 0x0 -- skip them rather than drawing a squashed
    // chart; the observer fires again once they're visible.
    if (rect.width < 1 || rect.height < 1) return;
    const newDpr = window.devicePixelRatio || 1;
    if (rect.width === cssW && rect.height === cssH && newDpr === dpr) return;
    cssW = rect.width;
    cssH = rect.height;
    dpr = newDpr;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    draw();
  }

  // --- interactions: pan, scroll-zoom, axis-drag rescale, hover tooltip ---
  const dragState = { mode: null, lastX: null, lastY: null };

  function regionFor(px, py) {
    const r = plotRect();
    if (px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h) return "plot";
    if (py >= r.y + r.h && py <= r.y + r.h + AXIS_STRIP && px >= r.x && px <= r.x + r.w) return "x";
    if (px >= r.x - AXIS_STRIP && px <= r.x && py >= r.y && py <= r.y + r.h) return "y";
    return null;
  }

  canvas.addEventListener("wheel", (e) => {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    if (regionFor(px, py) !== "plot") return;
    e.preventDefault();

    const zoomScale = 1.15;
    const scaleFactor = e.deltaY < 0 ? 1 / zoomScale : zoomScale;

    const xData = pxToX(px);
    const yData = pxToY(py);

    const [xFwd, xInv] = axisTransforms("linear");
    const [yFwd, yInv] = axisTransforms(yScale);

    const curXlim = [xFwd(view.xlim[0]), xFwd(view.xlim[1])];
    const curYlim = [yFwd(view.ylim[0]), yFwd(view.ylim[1])];

    const [newXlim, newYlim] = computeZoomedLimits(curXlim, curYlim, xFwd(xData), yFwd(yData), scaleFactor);

    view.xlim = [xInv(newXlim[0]), xInv(newXlim[1])];
    let lo = yInv(newYlim[0]), hi = yInv(newYlim[1]);
    if (yScale === "log" && lo <= 0) lo = 1e-6;
    view.ylim = [lo, hi];
    draw();
  }, { passive: false });

  canvas.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    const region = regionFor(px, py);
    if (region === "plot") dragState.mode = "pan";
    else if (region === "x") dragState.mode = "axis_x";
    else if (region === "y") dragState.mode = "axis_y";
    else return;
    dragState.lastX = px;
    dragState.lastY = py;
  });

  function onWindowMouseMove(e) {
    if (dragState.mode === null) return;
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    const r = plotRect();

    if (dragState.mode === "pan") {
      view.xlim = shiftLimits(view.xlim, px - dragState.lastX, r.w, "linear");
      let [lo, hi] = shiftLimits(view.ylim, py - dragState.lastY, r.h, yScale);
      if (yScale === "log" && lo <= 0) lo = 1e-6;
      view.ylim = [lo, hi];
    } else if (dragState.mode === "axis_x") {
      view.xlim = computeAxisDragRescale(view.xlim, px - dragState.lastX, r.w, "linear");
    } else if (dragState.mode === "axis_y") {
      // pixel y grows downward; dragging UP (toward smaller py, i.e.
      // negative delta in screen terms) should zoom in, matching the
      // "drag toward increasing axis value" convention.
      const dragPx = -(py - dragState.lastY);
      view.ylim = computeAxisDragRescale(view.ylim, dragPx, r.h, yScale);
      if (yScale === "log" && view.ylim[0] <= 0) view.ylim[0] = 1e-6;
    }

    dragState.lastX = px;
    dragState.lastY = py;
    draw();
  }

  function onWindowMouseUp() { dragState.mode = null; }

  // Window-level so a drag keeps working when the cursor leaves the
  // canvas. Removed again in destroy() so re-rendered charts don't pile
  // up stale listeners that keep old charts alive in memory.
  window.addEventListener("mousemove", onWindowMouseMove);
  window.addEventListener("mouseup", onWindowMouseUp);

  canvas.addEventListener("mousemove", (e) => {
    if (dragState.mode !== null) { tooltip.hidden = true; return; }
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    const r = plotRect();
    if (px < r.x || px > r.x + r.w || py < r.y || py > r.y + r.h) {
      tooltip.hidden = true;
      return;
    }
    const xData = pxToX(px);
    const idx = findNearestIndex(yearsAxis, xData);
    const xPoint = yearsAxis[idx], yPoint = medianPrices[idx];
    const pointPx = xToPx(xPoint), pointPy = yToPx(yPoint);

    tooltip.hidden = false;
    tooltip.textContent = `Year ${xPoint.toFixed(1)}   ${formatPrice(yPoint)}`;

    const xFrac = (pointPx - r.x) / r.w;
    const yFrac = 1 - (pointPy - r.y) / r.h;
    const flipX = xFrac > 0.5;
    const flipY = yFrac < 0.5;
    tooltip.style.left = pointPx + (flipX ? -8 : 8) + "px";
    tooltip.style.top = pointPy + (flipY ? -8 : 8) + "px";
    tooltip.style.transform = `translate(${flipX ? "-100%" : "0"}, ${flipY ? "-100%" : "0"})`;
  });

  canvas.addEventListener("mouseleave", () => { tooltip.hidden = true; });

  const ro = new ResizeObserver(resize);
  ro.observe(stage);
  resize();

  return {
    setYScale(scale) {
      yScale = scale;
      fitView();
      draw();
    },
    destroy() {
      ro.disconnect();
      window.removeEventListener("mousemove", onWindowMouseMove);
      window.removeEventListener("mouseup", onWindowMouseUp);
    },
  };
}
