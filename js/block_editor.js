/*
 * block_editor.js
 *
 * A node-graph "logic block" builder for custom strategies: condition
 * blocks (and logic gates combining several of them with AND/OR/NOT) are
 * dragged onto a canvas and wired into action blocks. Compiles directly
 * to the same Rule/Trigger/Action objects every other strategy in this
 * app uses -- see the "logic" trigger type in strategy.js for the
 * compound AND/OR/NOT conditions this requires from the engine.
 */

const BlockEditor = (function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  // ------------------------------------------------------------------
  // Block definitions: how each palette item renders, what parameters
  // it exposes, and how it compiles to the simulation engine's own
  // Trigger/Action objects (see strategy.js).
  // ------------------------------------------------------------------
  const NODE_DEFS = {
    condition_event: {
      kind: "condition",
      label: "Market Event",
      dot: "condition",
      params: [
        { key: "event", label: "Event", type: "select", options: Object.values(MarketEvent), default: MarketEvent.CRASH },
      ],
      toTrigger: (p) => new Trigger({ type: "event", event: p.event }),
    },
    condition_sequential_loss: {
      kind: "condition",
      label: "Losing Streak",
      dot: "condition",
      params: [{ key: "streak", label: "Months", type: "number", default: 2, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "sequential_loss", streak: p.streak }),
    },
    condition_sequential_gain: {
      kind: "condition",
      label: "Winning Streak",
      dot: "condition",
      params: [{ key: "streak", label: "Months", type: "number", default: 2, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "sequential_gain", streak: p.streak }),
    },
    condition_return_threshold: {
      kind: "condition",
      label: "Return Threshold",
      dot: "condition",
      params: [
        {
          key: "operator",
          label: "Compare",
          type: "select",
          options: [
            ["lte", "≤ (at most)"],
            ["lt", "< (less than)"],
            ["gte", "≥ (at least)"],
            ["gt", "> (more than)"],
          ],
          default: "lte",
        },
        { key: "value", label: "Return %", type: "number", default: -5, step: 0.5 },
      ],
      toTrigger: (p) => new Trigger({ type: "return_threshold", operator: p.operator, value: p.value / 100 }),
    },
    condition_drawdown_from_peak: {
      kind: "condition",
      label: "Drawdown From Peak",
      dot: "condition",
      params: [{ key: "value", label: "Drop %", type: "number", default: 20, min: 0, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "drawdown_from_peak", value: -Math.abs(p.value) / 100 }),
    },
    condition_above_price: {
      kind: "condition",
      label: "Above Price",
      dot: "condition",
      params: [{ key: "value", label: "Price (€)", type: "number", default: 150, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "price_threshold", operator: "gt", value: p.value }),
    },
    condition_below_price: {
      kind: "condition",
      label: "Below Price",
      dot: "condition",
      params: [{ key: "value", label: "Price (€)", type: "number", default: 80, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "price_threshold", operator: "lt", value: p.value }),
    },
    condition_ma_cross_up: {
      kind: "condition",
      label: "MA Cross Up",
      dot: "condition",
      params: [{ key: "period", label: "MA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ma_cross", period: p.period, direction: "up" }),
    },
    condition_ma_cross_down: {
      kind: "condition",
      label: "MA Cross Down",
      dot: "condition",
      params: [{ key: "period", label: "MA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ma_cross", period: p.period, direction: "down" }),
    },
    condition_above_ma: {
      kind: "condition",
      label: "Above MA",
      dot: "condition",
      params: [{ key: "period", label: "MA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ma_state", period: p.period, side: "above" }),
    },
    condition_below_ma: {
      kind: "condition",
      label: "Below MA",
      dot: "condition",
      params: [{ key: "period", label: "MA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ma_state", period: p.period, side: "below" }),
    },
    condition_fast_ma_cross_up: {
      kind: "condition",
      label: "Fast MA Cross Up",
      dot: "condition",
      params: [
        { key: "fastPeriod", label: "Fast Months", type: "number", default: 3, min: 1, step: 1 },
        { key: "slowPeriod", label: "Slow Months", type: "number", default: 12, min: 1, step: 1 },
      ],
      toTrigger: (p) => new Trigger({ type: "ma_dual_cross", fastPeriod: p.fastPeriod, slowPeriod: p.slowPeriod, direction: "up" }),
    },
    condition_fast_ma_cross_down: {
      kind: "condition",
      label: "Fast MA Cross Down",
      dot: "condition",
      params: [
        { key: "fastPeriod", label: "Fast Months", type: "number", default: 3, min: 1, step: 1 },
        { key: "slowPeriod", label: "Slow Months", type: "number", default: 12, min: 1, step: 1 },
      ],
      toTrigger: (p) => new Trigger({ type: "ma_dual_cross", fastPeriod: p.fastPeriod, slowPeriod: p.slowPeriod, direction: "down" }),
    },
    condition_ema_cross_up: {
      kind: "condition",
      label: "EMA Cross Up",
      dot: "condition",
      params: [{ key: "period", label: "EMA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ema_cross", period: p.period, direction: "up" }),
    },
    condition_ema_cross_down: {
      kind: "condition",
      label: "EMA Cross Down",
      dot: "condition",
      params: [{ key: "period", label: "EMA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ema_cross", period: p.period, direction: "down" }),
    },
    condition_above_ema: {
      kind: "condition",
      label: "Above EMA",
      dot: "condition",
      params: [{ key: "period", label: "EMA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ema_state", period: p.period, side: "above" }),
    },
    condition_below_ema: {
      kind: "condition",
      label: "Below EMA",
      dot: "condition",
      params: [{ key: "period", label: "EMA Months", type: "number", default: 12, min: 1, step: 1 }],
      toTrigger: (p) => new Trigger({ type: "ema_state", period: p.period, side: "below" }),
    },
    condition_rsi_above: {
      kind: "condition",
      label: "RSI Above",
      dot: "condition",
      params: [
        { key: "period", label: "RSI Months", type: "number", default: 14, min: 1, step: 1 },
        { key: "value", label: "RSI Level", type: "number", default: 70, min: 0, max: 100, step: 1 },
      ],
      toTrigger: (p) => new Trigger({ type: "rsi_threshold", period: p.period, operator: "gte", value: p.value }),
    },
    condition_rsi_below: {
      kind: "condition",
      label: "RSI Below",
      dot: "condition",
      params: [
        { key: "period", label: "RSI Months", type: "number", default: 14, min: 1, step: 1 },
        { key: "value", label: "RSI Level", type: "number", default: 30, min: 0, max: 100, step: 1 },
      ],
      toTrigger: (p) => new Trigger({ type: "rsi_threshold", period: p.period, operator: "lte", value: p.value }),
    },
    logic_all: {
      kind: "logic",
      label: "ALL of these",
      dot: "logic",
      mode: "all",
      params: [],
    },
    logic_any: {
      kind: "logic",
      label: "ANY of these",
      dot: "logic",
      mode: "any",
      params: [],
    },
    logic_not: {
      kind: "logic",
      label: "NOT",
      dot: "logic",
      mode: "not",
      params: [],
    },
    action_multiply: {
      kind: "action",
      label: "Multiply Buy",
      dot: "action",
      params: [{ key: "value", label: "Factor ×", type: "number", default: 2, step: 0.1 }],
      toAction: (p) => new Action({ type: "multiply", value: p.value }),
    },
    action_set_fixed: {
      kind: "action",
      label: "Set Fixed Buy",
      dot: "action",
      params: [
        { key: "allCash", label: "Use all available cash", type: "checkbox", default: false },
        { key: "value", label: "Amount (€)", type: "number", default: 500, step: 50, showIf: (p) => !p.allCash },
      ],
      toAction: (p) => new Action({ type: "set_fixed", value: p.allCash ? Infinity : p.value }),
    },
    action_add_fixed: {
      kind: "action",
      label: "Add To Buy",
      dot: "action",
      params: [{ key: "value", label: "Amount (€)", type: "number", default: 200, step: 50 }],
      toAction: (p) => new Action({ type: "add_fixed", value: p.value }),
    },
    action_skip: {
      kind: "action",
      label: "Skip Buy",
      dot: "action",
      params: [],
      toAction: () => new Action({ type: "skip" }),
    },
    action_scale_with_streak: {
      kind: "action",
      label: "Scale With Streak",
      dot: "action",
      params: [
        { key: "start", label: "Start ×", type: "number", default: 1, step: 0.1 },
        { key: "increment", label: "+ per month", type: "number", default: 1, step: 0.1 },
        { key: "cap", label: "Cap", type: "number", default: null, step: 0.1, optional: true },
      ],
      toAction: (p) =>
        new Action({
          type: "scale_with_streak",
          start: p.start,
          increment: p.increment,
          cap: p.cap === null || p.cap === undefined || p.cap === "" ? null : Number(p.cap),
        }),
      hint: "Only reads the actual streak length when connected directly to a Losing/Winning Streak condition (not through a logic gate).",
    },
  };

  function defKey(node) {
    return `${node.kind}_${node.type}`;
  }
  function nodeDef(node) {
    return NODE_DEFS[defKey(node)];
  }

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  let nodes = [];
  let edges = [];
  let nextNodeId = 1;
  let nextEdgeId = 1;

  let paletteEl, viewportEl, canvasEl, svgEl, emptyHintEl, clearBtn;
  let mounted = false;

  function nodesById(id) {
    return nodes.find((n) => n.id === id) || null;
  }

  // ------------------------------------------------------------------
  // Graph mutation
  // ------------------------------------------------------------------
  function addNode(kind, type, x, y) {
    const def = NODE_DEFS[`${kind}_${type}`];
    if (!def) return;
    const params = {};
    for (const p of def.params) params[p.key] = p.default;
    const node = { id: "n" + nextNodeId++, kind, type, params, x: Math.max(4, x), y: Math.max(4, y) };
    nodes.push(node);
    renderAll();
  }

  function removeNode(id) {
    nodes = nodes.filter((n) => n.id !== id);
    edges = edges.filter((e) => e.from !== id && e.to !== id);
    renderAll();
  }

  function removeEdge(id) {
    edges = edges.filter((e) => e.id !== id);
    renderAll();
  }

  function wouldCreateCycle(fromId, toId) {
    const stack = [toId];
    const seen = new Set();
    while (stack.length) {
      const cur = stack.pop();
      if (cur === fromId) return true;
      if (seen.has(cur)) continue;
      seen.add(cur);
      for (const e of edges) if (e.from === cur) stack.push(e.to);
    }
    return false;
  }

  function connect(fromId, toId) {
    if (fromId === toId) return;
    const fromNode = nodesById(fromId);
    const toNode = nodesById(toId);
    if (!fromNode || !toNode) return;
    if (fromNode.kind === "action" || toNode.kind === "condition") return; // no output / no input
    if (wouldCreateCycle(fromId, toId)) {
      if (window.showAppError) window.showAppError("That connection would create a loop.");
      return;
    }
    if (toNode.kind === "action" || (toNode.kind === "logic" && toNode.type === "not")) {
      // Actions and NOT gates take exactly one input -- a new connection replaces any existing one.
      edges = edges.filter((e) => e.to !== toId);
    }
    edges.push({ id: "e" + nextEdgeId++, from: fromId, to: toId });
    renderAll();
  }

  function clearAll() {
    nodes = [];
    edges = [];
    renderAll();
  }

  // ------------------------------------------------------------------
  // Compiling to the simulation engine
  // ------------------------------------------------------------------
  function buildTrigger(nodeId, guard) {
    guard = guard || new Set();
    if (guard.has(nodeId)) return null;
    guard.add(nodeId);
    const node = nodesById(nodeId);
    if (!node) return null;
    const def = nodeDef(node);
    if (node.kind === "condition") return def.toTrigger(node.params);
    if (node.kind === "logic") {
      const childIds = edges.filter((e) => e.to === nodeId).map((e) => e.from);
      const children = childIds.map((id) => buildTrigger(id, guard)).filter(Boolean);
      if (!children.length) return null;
      return new Trigger({ type: "logic", mode: def.mode, children });
    }
    return null;
  }

  function compile() {
    const rules = [];
    const actionNodes = nodes.filter((n) => n.kind === "action").sort((a, b) => a.y - b.y || a.x - b.x);
    for (const node of actionNodes) {
      const inEdge = edges.find((e) => e.to === node.id);
      if (!inEdge) continue;
      const trigger = buildTrigger(inEdge.from);
      if (!trigger) continue;
      const action = nodeDef(node).toAction(node.params);
      rules.push(new Rule(trigger, action));
    }
    return rules;
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------
  function portPos(nodeId, side) {
    const nodeEl = canvasEl.querySelector(`.be-node[data-node-id="${nodeId}"]`);
    if (!nodeEl) return null;
    const portEl = nodeEl.querySelector(side === "out" ? ".be-port-out" : ".be-port-in");
    if (!portEl) return null;
    return {
      x: nodeEl.offsetLeft + portEl.offsetLeft + portEl.offsetWidth / 2,
      y: nodeEl.offsetTop + portEl.offsetTop + portEl.offsetHeight / 2,
    };
  }

  function bezierPath(p0, p1) {
    const dx = Math.max(40, Math.abs(p1.x - p0.x) / 2);
    return `M ${p0.x} ${p0.y} C ${p0.x + dx} ${p0.y}, ${p1.x - dx} ${p1.y}, ${p1.x} ${p1.y}`;
  }

  function renderConnections() {
    const w = Math.max(canvasEl.scrollWidth, canvasEl.clientWidth);
    const h = Math.max(canvasEl.scrollHeight, canvasEl.clientHeight);
    svgEl.setAttribute("width", w);
    svgEl.setAttribute("height", h);
    svgEl.innerHTML = "";
    for (const e of edges) {
      const p0 = portPos(e.from, "out");
      const p1 = portPos(e.to, "in");
      if (!p0 || !p1) continue;
      const d = bezierPath(p0, p1);

      const hit = document.createElementNS(SVG_NS, "path");
      hit.setAttribute("d", d);
      hit.setAttribute("class", "be-edge-hit");
      hit.addEventListener("click", () => removeEdge(e.id));
      svgEl.appendChild(hit);

      const visible = document.createElementNS(SVG_NS, "path");
      visible.setAttribute("d", d);
      visible.setAttribute("class", "be-edge");
      svgEl.appendChild(visible);
    }
  }

  function renderNodePosition(node) {
    const el = canvasEl.querySelector(`.be-node[data-node-id="${node.id}"]`);
    if (el) {
      el.style.left = node.x + "px";
      el.style.top = node.y + "px";
    }
  }

  function attachNodeDrag(node, headerEl) {
    headerEl.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".be-node-delete")) return;
      e.stopPropagation();
      e.preventDefault();
      const startX = e.clientX,
        startY = e.clientY;
      const origX = node.x,
        origY = node.y;
      function onMove(ev) {
        node.x = Math.max(0, origX + (ev.clientX - startX));
        node.y = Math.max(0, origY + (ev.clientY - startY));
        renderNodePosition(node);
        renderConnections();
      }
      function onUp() {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
  }

  function attachOutputPortDrag(portEl, node) {
    portEl.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const tempPath = document.createElementNS(SVG_NS, "path");
      tempPath.setAttribute("class", "be-edge be-edge-temp");
      svgEl.appendChild(tempPath);

      function update(clientX, clientY) {
        const canvasRect = canvasEl.getBoundingClientRect();
        const start = portPos(node.id, "out");
        if (!start) return;
        const end = { x: clientX - canvasRect.left, y: clientY - canvasRect.top };
        tempPath.setAttribute("d", bezierPath(start, end));
      }
      function onMove(ev) {
        update(ev.clientX, ev.clientY);
      }
      function onUp(ev) {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        tempPath.remove();
        const target = document.elementFromPoint(ev.clientX, ev.clientY);
        const inputPortEl = target && target.closest(".be-port-in");
        if (inputPortEl) connect(node.id, inputPortEl.dataset.nodeId);
      }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      update(e.clientX, e.clientY);
    });
  }

  function renderNode(node) {
    const def = nodeDef(node);
    const el = document.createElement("div");
    el.className = `be-node be-node-${node.kind}`;
    el.style.left = node.x + "px";
    el.style.top = node.y + "px";
    el.dataset.nodeId = node.id;
    if (def.hint) el.title = def.hint;

    const header = document.createElement("div");
    header.className = "be-node-header";
    const dot = document.createElement("span");
    dot.className = `be-dot be-dot-${def.dot}`;
    const title = document.createElement("span");
    title.className = "be-node-title";
    title.textContent = def.label;
    const del = document.createElement("button");
    del.type = "button";
    del.className = "be-node-delete";
    del.textContent = "×";
    del.setAttribute("aria-label", `Remove ${def.label} block`);
    del.addEventListener("click", (ev) => {
      ev.stopPropagation();
      removeNode(node.id);
    });
    header.appendChild(dot);
    header.appendChild(title);
    header.appendChild(del);
    el.appendChild(header);
    attachNodeDrag(node, header);

    if (def.params.length) {
      const body = document.createElement("div");
      body.className = "be-node-body";
      for (const p of def.params) {
        if (p.showIf && !p.showIf(node.params)) continue;
        const row = document.createElement("label");
        row.className = "be-param-row";
        const span = document.createElement("span");
        span.textContent = p.label;
        row.appendChild(span);

        let input;
        if (p.type === "select") {
          input = document.createElement("select");
          for (const opt of p.options) {
            const [val, label] = Array.isArray(opt) ? opt : [opt, opt];
            const o = document.createElement("option");
            o.value = val;
            o.textContent = label;
            if (node.params[p.key] === val) o.selected = true;
            input.appendChild(o);
          }
        } else if (p.type === "checkbox") {
          input = document.createElement("input");
          input.type = "checkbox";
          input.checked = !!node.params[p.key];
        } else {
          input = document.createElement("input");
          input.type = "text";
          input.inputMode = "decimal";
          input.value = node.params[p.key] === null || node.params[p.key] === undefined ? "" : node.params[p.key];
        }
        input.addEventListener("pointerdown", (ev) => ev.stopPropagation());
        input.addEventListener("change", () => {
          if (p.type === "checkbox") {
            node.params[p.key] = input.checked;
          } else if (p.type === "select") {
            node.params[p.key] = input.value;
          } else {
            const raw = input.value.trim();
            if (raw === "" && p.optional) {
              node.params[p.key] = null;
            } else {
              const num = Number(raw);
              node.params[p.key] = Number.isFinite(num) ? num : node.params[p.key];
            }
          }
          renderAll();
        });
        row.appendChild(input);
        body.appendChild(row);
      }
      if (body.children.length) el.appendChild(body);
    }

    if (node.kind !== "condition") {
      const inPort = document.createElement("div");
      inPort.className = "be-port be-port-in";
      inPort.dataset.nodeId = node.id;
      el.appendChild(inPort);
    }
    if (node.kind !== "action") {
      const outPort = document.createElement("div");
      outPort.className = "be-port be-port-out";
      attachOutputPortDrag(outPort, node);
      el.appendChild(outPort);
    }

    if (node.kind === "logic") {
      const count = edges.filter((e) => e.to === node.id).length;
      const badge = document.createElement("div");
      badge.className = "be-badge" + (count === 0 ? " be-badge-warn" : "");
      badge.textContent = count === 0 ? "no inputs" : `${count} input${count === 1 ? "" : "s"}`;
      el.appendChild(badge);
    }
    if (node.kind === "action") {
      const connected = edges.some((e) => e.to === node.id);
      if (!connected) {
        const badge = document.createElement("div");
        badge.className = "be-badge be-badge-warn";
        badge.textContent = "not connected";
        el.appendChild(badge);
      }
    }

    canvasEl.appendChild(el);
  }

  function renderAll() {
    canvasEl.querySelectorAll(".be-node").forEach((n) => n.remove());
    for (const node of nodes) renderNode(node);
    renderConnections();
    if (emptyHintEl) emptyHintEl.hidden = nodes.length > 0;
  }

  // ------------------------------------------------------------------
  // Palette drag-to-create
  // ------------------------------------------------------------------
  function positionGhost(ghost, x, y) {
    ghost.style.left = x + "px";
    ghost.style.top = y + "px";
  }

  function attachPaletteDrag(itemEl) {
    itemEl.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const kind = itemEl.dataset.kind;
      const type = itemEl.dataset.type;

      const ghost = itemEl.cloneNode(true);
      ghost.classList.add("be-ghost");
      document.body.appendChild(ghost);
      positionGhost(ghost, e.clientX, e.clientY);

      function onMove(ev) {
        positionGhost(ghost, ev.clientX, ev.clientY);
      }
      function stop() {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", stop);
        ghost.remove();
      }
      function onUp(ev) {
        stop();
        const vpRect = viewportEl.getBoundingClientRect();
        if (ev.clientX >= vpRect.left && ev.clientX <= vpRect.right && ev.clientY >= vpRect.top && ev.clientY <= vpRect.bottom) {
          const canvasRect = canvasEl.getBoundingClientRect();
          addNode(kind, type, ev.clientX - canvasRect.left - 85, ev.clientY - canvasRect.top - 18);
        }
      }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      // On a phone a sideways swipe scrolls the palette strip instead (see
      // .palette-item in the CSS); the browser then cancels the pointer.
      window.addEventListener("pointercancel", stop);
    });
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------
  function mount() {
    if (mounted) return;
    paletteEl = document.getElementById("be-palette");
    viewportEl = document.getElementById("be-viewport");
    canvasEl = document.getElementById("be-canvas");
    svgEl = document.getElementById("be-svg");
    emptyHintEl = document.getElementById("be-empty-hint");
    clearBtn = document.getElementById("be-clear");
    if (!paletteEl || !canvasEl) return;

    paletteEl.querySelectorAll(".palette-item").forEach(attachPaletteDrag);
    clearBtn.addEventListener("click", clearAll);

    mounted = true;
    renderAll();
  }

  return { mount, compile, clearAll };
})();
