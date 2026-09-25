/*
 * app.js
 *
 * UI wiring: the settings/chart/output layout and its behaviors
 * (data-source lock, custom strategy builder, Compare All table/graph
 * toggle, log/linear chart toggle).
 *
 * Saved custom strategies live only in memory for this page load --
 * gone once you close or reload the tab.
 */

(function () {
  "use strict";

  const CUSTOM_LABEL = "Custom...";
  const MAX_SAVED_STRATEGIES = 10;
  const MAX_STRATEGY_NAME_CHARS = 28;

  const state = {
    previousPrices: null,
    customStrategy: null,
    savedStrategies: [],
    lastSingleResult: null, // { result, name, description }
    chartScale: "linear",
    priceSettingsLocked: false,
    unlockedPriceSettings: null,
    compareMode: false,
    compareView: null, // "table" | "graph"
    lastCompareRows: null,
    lastCompareMarketResult: null,
    chartController: null,
    compareChartController: null,
  };

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------
  const el = {
    layout: document.getElementById("layout"),

    startPrice: document.getElementById("f-start-price"),
    years: document.getElementById("f-years"),
    numRuns: document.getElementById("f-num-runs"),
    dataSource: document.getElementById("f-data-source"),
    savings: document.getElementById("f-savings"),
    income: document.getElementById("f-income"),
    strategy: document.getElementById("f-strategy"),
    customStatus: document.getElementById("custom-strategy-status"),

    btnRun: document.getElementById("btn-run"),
    btnQuick: document.getElementById("btn-quick"),
    btnCompare: document.getElementById("btn-compare"),
    btnSwitchGraph: document.getElementById("btn-switch-graph"),
    btnScaleToggle: document.getElementById("btn-scale-toggle"),

    chartPlaceholder: document.getElementById("chart-placeholder"),
    chartHost: document.getElementById("chart-host"),

    outputInitial: document.getElementById("output-initial"),
    outputContent: document.getElementById("output-content"),
    compareContent: document.getElementById("compare-content"),

    modal: document.getElementById("custom-modal"),
    csName: document.getElementById("cs-name"),
    csDescription: document.getElementById("cs-description"),
    csSaveBtn: document.getElementById("cs-save-btn"),
    csCancel: document.getElementById("cs-cancel"),

    toast: document.getElementById("error-toast"),
  };

  let toastTimer = null;
  function showError(message) {
    el.toast.textContent = message;
    el.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.toast.hidden = true; }, 5000);
  }
  // block_editor.js has no access to this module's private showError, so
  // it reports cycle-detection errors (the only failure mode inside the
  // block graph itself) through this global instead.
  window.showAppError = showError;

  // ------------------------------------------------------------------
  // Strategy dropdown
  // ------------------------------------------------------------------
  function buildStrategyDropdownValues() {
    return [...PRESET_NAMES, ...state.savedStrategies.map((s) => s.name), CUSTOM_LABEL];
  }

  function populateStrategyDropdown(selectValue) {
    const prev = selectValue ?? el.strategy.value;
    el.strategy.innerHTML = "";
    for (const name of buildStrategyDropdownValues()) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      el.strategy.appendChild(opt);
    }
    if ([...el.strategy.options].some((o) => o.value === prev)) {
      el.strategy.value = prev;
    }
  }
  populateStrategyDropdown(PRESET_NAMES[0]);

  el.strategy.addEventListener("change", () => {
    if (el.strategy.value === CUSTOM_LABEL) {
      openCustomStrategyModal();
    }
  });

  function uniqueStrategyName(base) {
    const taken = new Set([...PRESET_NAMES, ...state.savedStrategies.map((s) => s.name), CUSTOM_LABEL]);
    if (!taken.has(base)) return base;
    let suffix = 2;
    while (taken.has(`${base} (${suffix})`)) suffix += 1;
    return `${base} (${suffix})`;
  }

  function setCustomStrategyStatus(strategy) {
    el.customStatus.textContent = `✓ '${strategy.name}' (${strategy.rules.length} rule(s) set)`;
  }

  // ------------------------------------------------------------------
  // Custom Strategy modal -- a logic-block graph builder (condition and
  // logic-gate blocks wired into action blocks on a canvas) rather than
  // a flat per-event multiplier form. See block_editor.js.
  // ------------------------------------------------------------------
  BlockEditor.mount();

  function openCustomStrategyModal() {
    el.modal.hidden = false;
  }

  function closeCustomStrategyModal() {
    el.modal.hidden = true;
  }

  el.csSaveBtn.addEventListener("click", () => {
    const rules = BlockEditor.compile();
    if (!rules.length) {
      showError("Connect at least one action block to a condition (or a logic gate) before saving.");
      return;
    }

    const name = el.csName.value.trim() || "Custom Strategy";
    const description = el.csDescription.value.trim();
    const strategy = new Strategy({ name, rules, description });

    closeCustomStrategyModal();
    onCustomStrategyDone(strategy);
  });

  el.csCancel.addEventListener("click", () => {
    closeCustomStrategyModal();
    if (state.customStrategy === null) {
      el.strategy.value = PRESET_NAMES[0];
    }
  });

  // Every custom strategy built via Save is saved to the dropdown for the
  // rest of this session (up to MAX_SAVED_STRATEGIES) -- there's no
  // separate opt-in for it.
  function onCustomStrategyDone(strategy) {
    state.customStrategy = strategy;

    if (state.savedStrategies.length >= MAX_SAVED_STRATEGIES) {
      showError(
        `You can save up to ${MAX_SAVED_STRATEGIES} custom strategies, and that limit has been reached. ` +
        `This strategy is still usable for this session via 'Custom...', just not saved to the dropdown.`
      );
      setCustomStrategyStatus(strategy);
      return;
    }
    strategy.name = uniqueStrategyName(strategy.name);
    state.savedStrategies.push(strategy);
    populateStrategyDropdown(strategy.name);
    el.strategy.value = strategy.name;
    setCustomStrategyStatus(strategy);
  }

  // ------------------------------------------------------------------
  // Data source lock (Start price / Years / Number of runs)
  // ------------------------------------------------------------------
  function lockedInputs() {
    return [el.startPrice, el.years, el.numRuns];
  }

  function formatG(v) {
    // Mimics Python's "{:g}" for the handful of values this sees.
    if (Number.isInteger(v)) return String(v);
    return String(parseFloat(v.toPrecision(6)));
  }

  function priceSettingsFromPrevious() {
    const series = state.previousPrices;
    return {
      startPrice: formatG(series[0][0]),
      years: String((series[0].length - 1) / 12),
      numRuns: String(series.length),
    };
  }

  el.dataSource.addEventListener("change", () => {
    if (el.dataSource.value === "reuse") {
      if (state.previousPrices === null) {
        showError("No previous run to reuse yet -- run once with 'Generate new data' first.");
        el.dataSource.value = "new";
        return;
      }
      lockPriceSettings();
    } else {
      unlockPriceSettings();
    }
  });

  function lockPriceSettings() {
    if (state.priceSettingsLocked) return;
    state.priceSettingsLocked = true;
    state.unlockedPriceSettings = {
      startPrice: el.startPrice.value,
      years: el.years.value,
      numRuns: el.numRuns.value,
    };
    syncLockedPriceSettings();
    for (const input of lockedInputs()) input.readOnly = true;
  }

  function unlockPriceSettings() {
    if (!state.priceSettingsLocked) return;
    state.priceSettingsLocked = false;
    const stashed = state.unlockedPriceSettings;
    if (stashed) {
      el.startPrice.value = stashed.startPrice;
      el.years.value = stashed.years;
      el.numRuns.value = stashed.numRuns;
    }
    state.unlockedPriceSettings = null;
    for (const input of lockedInputs()) input.readOnly = false;
  }

  function syncLockedPriceSettings() {
    if (!state.priceSettingsLocked || state.previousPrices === null) return;
    const values = priceSettingsFromPrevious();
    el.startPrice.value = values.startPrice;
    el.years.value = values.years;
    el.numRuns.value = values.numRuns;
  }

  // ------------------------------------------------------------------
  // Strategy lookup + input parsing
  // ------------------------------------------------------------------
  function getSelectedStrategy() {
    const name = el.strategy.value;
    if (name === CUSTOM_LABEL) {
      if (state.customStrategy === null) {
        showError("Select 'Custom...' again and fill in the dialog first.");
        return null;
      }
      return state.customStrategy;
    }
    for (const [presetName, factory] of Object.values(ALL_PRESETS)) {
      if (presetName === name) return factory();
    }
    for (const saved of state.savedStrategies) {
      if (saved.name === name) return saved;
    }
    return null;
  }

  function parseInvestingInputs() {
    const startPrice = Number(el.startPrice.value.trim());
    const yearsRaw = el.years.value.trim();
    const numRunsRaw = el.numRuns.value.trim();
    const savings = Number(el.savings.value.trim());
    const income = Number(el.income.value.trim());

    const yearsValid = /^-?\d+$/.test(yearsRaw);
    const numRunsValid = /^-?\d+$/.test(numRunsRaw);
    const years = yearsValid ? parseInt(yearsRaw, 10) : NaN;
    const numRuns = numRunsValid ? parseInt(numRunsRaw, 10) : NaN;

    if (!Number.isFinite(startPrice) || !Number.isFinite(savings) || !Number.isFinite(income) ||
        !yearsValid || !numRunsValid) {
      showError("Please make sure every field contains a valid number.");
      return null;
    }
    if (startPrice <= 0 || years <= 0 || numRuns <= 0) {
      showError("Start price, years, and number of runs must all be positive.");
      return null;
    }
    if (savings < 0 || income < 0) {
      showError("Starting savings and monthly income cannot be negative.");
      return null;
    }

    return { startPrice, years, startingSavings: savings, monthlyIncome: income, numRuns };
  }

  // ------------------------------------------------------------------
  // Run actions
  // ------------------------------------------------------------------
  el.btnRun.addEventListener("click", () => {
    const inputs = parseInvestingInputs();
    if (!inputs) return;
    const strategy = getSelectedStrategy();
    if (!strategy) return;

    const wantsReuse = el.dataSource.value === "reuse";
    if (wantsReuse && state.previousPrices === null) {
      showError("No previous run to reuse yet -- run once with 'Generate new data' first.");
      return;
    }

    const priceParams = { startPrice: inputs.startPrice, years: inputs.years };
    const reuse = wantsReuse ? state.previousPrices : null;

    const result = runBacktest({
      strategy,
      priceParams,
      startingSavings: inputs.startingSavings,
      monthlyIncome: inputs.monthlyIncome,
      numRuns: inputs.numRuns,
      reusePrices: reuse,
    });

    state.previousPrices = result.priceSeriesUsed;
    syncLockedPriceSettings();
    restoreNormalLayout();
    renderInvestingResults(result, strategy.name, strategy.description);
  });

  el.btnQuick.addEventListener("click", () => {
    const factory = ALL_PRESETS["1"][1];
    const strategy = factory();
    const priceParams = { startPrice: 100.0, years: 50 };
    const result = runBacktest({
      strategy,
      priceParams,
      startingSavings: 10000.0,
      monthlyIncome: 300.0,
      numRuns: 50,
      reusePrices: null,
    });
    state.previousPrices = result.priceSeriesUsed;
    syncLockedPriceSettings();
    restoreNormalLayout();
    renderInvestingResults(result, strategy.name, strategy.description);
  });

  el.btnCompare.addEventListener("click", () => {
    const inputs = parseInvestingInputs();
    if (!inputs) return;

    const strategies = Object.values(ALL_PRESETS).map(([, factory]) => factory());
    strategies.push(...state.savedStrategies);
    if (state.customStrategy !== null && !state.savedStrategies.includes(state.customStrategy)) {
      strategies.push(state.customStrategy);
    }

    const priceParams = { startPrice: inputs.startPrice, years: inputs.years };
    try {
      const { rows, marketResult } = compareStrategies({
        strategies,
        priceParams,
        startingSavings: inputs.startingSavings,
        monthlyIncome: inputs.monthlyIncome,
        numRuns: inputs.numRuns,
      });
      state.lastCompareRows = rows;
      state.lastCompareMarketResult = marketResult;
      state.previousPrices = marketResult.priceSeriesUsed;
      syncLockedPriceSettings();
      enterCompareMode();
      showCompareTable();
    } catch (exc) {
      showError(`Compare All failed: ${exc.message || exc}`);
      restoreNormalLayout();
    }
  });

  // ------------------------------------------------------------------
  // Compare mode layout
  // ------------------------------------------------------------------
  function enterCompareMode() {
    if (state.compareMode) return;
    state.compareMode = true;
    el.layout.classList.add("compare-mode");
    el.btnSwitchGraph.hidden = false;
  }

  function restoreNormalLayout() {
    if (!state.compareMode) return;
    state.compareMode = false;
    state.compareView = null;
    el.layout.classList.remove("compare-mode");
    el.btnSwitchGraph.hidden = true;
    el.btnSwitchGraph.textContent = "Switch to Graph";
    if (state.compareChartController) {
      state.compareChartController.destroy();
      state.compareChartController = null;
    }
    el.compareContent.hidden = true;
    if (state.lastSingleResult) {
      el.outputContent.hidden = false;
      el.outputInitial.hidden = true;
    } else {
      el.outputInitial.hidden = false;
      el.outputContent.hidden = true;
    }
  }

  el.btnSwitchGraph.addEventListener("click", () => {
    if (state.compareView === "table") showCompareGraph();
    else showCompareTable();
  });

  el.btnScaleToggle.addEventListener("click", () => {
    state.chartScale = state.chartScale === "linear" ? "log" : "linear";
    el.btnScaleToggle.textContent = state.chartScale === "log" ? "View Linear Graph" : "View Log Graph";

    if (state.compareMode && state.compareView === "graph") {
      showCompareGraph();
    } else if (!state.compareMode && state.lastSingleResult) {
      const { result, name, description } = state.lastSingleResult;
      renderInvestingResults(result, name, description);
    }
  });

  function showCompareTable() {
    state.compareView = "table";
    el.btnSwitchGraph.textContent = "Switch to Graph";
    if (state.compareChartController) {
      state.compareChartController.destroy();
      state.compareChartController = null;
    }
    el.outputInitial.hidden = true;
    el.outputContent.hidden = true;
    el.compareContent.hidden = false;
    renderComparisonTable(state.lastCompareRows);
  }

  function showCompareGraph() {
    state.compareView = "graph";
    el.btnSwitchGraph.textContent = "Switch to Table";
    el.outputInitial.hidden = true;
    el.outputContent.hidden = true;
    el.compareContent.hidden = false;

    el.compareContent.innerHTML = "";
    const header = document.createElement("div");
    header.className = "compare-header";
    header.innerHTML = `<h1 class="panel-title" style="margin:0;">Data Used for Comparison</h1>`;
    el.compareContent.appendChild(header);

    if (state.compareChartController) {
      state.compareChartController.destroy();
      state.compareChartController = null;
    }

    if (state.lastCompareMarketResult) {
      const wrap = document.createElement("div");
      wrap.className = "compare-graph-wrap";
      el.compareContent.appendChild(wrap);
      // Mount into a padding-free inner host: the wrap keeps its padding
      // for spacing, the host is exactly the drawable area.
      const host = document.createElement("div");
      wrap.appendChild(host);
      state.compareChartController = mountChartFromResult(host, state.lastCompareMarketResult);
    } else {
      const note = document.createElement("p");
      note.className = "empty-note";
      note.textContent = "No comparison data yet -- click 'Compare All' first.";
      el.compareContent.appendChild(note);
    }
  }

  function renderComparisonTable(rows) {
    el.compareContent.innerHTML = "";
    const header = document.createElement("div");
    header.className = "compare-header";
    header.innerHTML = `<h1 class="panel-title" style="margin:0;">Compare All</h1>`;
    el.compareContent.appendChild(header);

    const wrap = document.createElement("div");
    wrap.className = "compare-table-wrap";
    el.compareContent.appendChild(wrap);

    const table = document.createElement("table");
    table.className = "compare-table";
    const columns = ["Strategy", "Total Return", "Annualized", "Capital Efficiency", "Ending Value", "Max Drawdown", "Gap to Best"];
    const thead = document.createElement("thead");
    const trHead = document.createElement("tr");
    for (const c of columns) {
      const th = document.createElement("th");
      th.textContent = c;
      trHead.appendChild(th);
    }
    thead.appendChild(trHead);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    const total = rows.length;

    const drawdowns = rows.map((r) => r.medianMaxDrawdownPct);
    const drawdownOrder = drawdowns.map((_, i) => i).sort((a, b) => drawdowns[b] - drawdowns[a]);
    const drawdownRank = {};
    drawdownOrder.forEach((rowI, rank) => { drawdownRank[rowI] = rank; });

    const efficiencies = rows.map((r) => r.medianCapitalEfficiencyPct);
    const efficiencyOrder = efficiencies.map((_, i) => i).sort((a, b) => efficiencies[b] - efficiencies[a]);
    const efficiencyRank = {};
    efficiencyOrder.forEach((rowI, rank) => { efficiencyRank[rowI] = rank; });

    rows.forEach((row, i) => {
      const tr = document.createElement("tr");

      let name = row.name;
      if (name.length > MAX_STRATEGY_NAME_CHARS) name = name.slice(0, MAX_STRATEGY_NAME_CHARS - 1) + "…";
      const tdName = document.createElement("td");
      tdName.textContent = name;
      tr.appendChild(tdName);

      const returnColor = getRankColor(i, total);
      const tdReturn = document.createElement("td");
      tdReturn.textContent = `${row.medianReturnPct.toFixed(2)}%`;
      if (returnColor) { tdReturn.style.color = returnColor; tdReturn.classList.add("rank-colored"); }
      tr.appendChild(tdReturn);

      const tdAnnual = document.createElement("td");
      tdAnnual.textContent = `${row.medianAnnualReturnPct.toFixed(2)}%`;
      tr.appendChild(tdAnnual);

      const effColor = getRankColor(efficiencyRank[i], total);
      const tdEff = document.createElement("td");
      tdEff.textContent = `${row.medianCapitalEfficiencyPct.toFixed(2)}%`;
      if (effColor) { tdEff.style.color = effColor; tdEff.classList.add("rank-colored"); }
      tr.appendChild(tdEff);

      const tdEnding = document.createElement("td");
      tdEnding.textContent = `€${Math.round(row.medianEndingPortfolioValue).toLocaleString("en-US")}`;
      tr.appendChild(tdEnding);

      const ddColor = getRankColor(drawdownRank[i], total);
      const tdDd = document.createElement("td");
      tdDd.textContent = `${row.medianMaxDrawdownPct.toFixed(2)}%`;
      if (ddColor) { tdDd.style.color = ddColor; tdDd.classList.add("rank-colored"); }
      tr.appendChild(tdDd);

      const tdGap = document.createElement("td");
      tdGap.textContent = row.returnGapPct === 0 ? "—" : `-${row.returnGapPct.toFixed(2)}%`;
      tr.appendChild(tdGap);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  // ------------------------------------------------------------------
  // Single-strategy results (chart + stats card)
  // ------------------------------------------------------------------
  function mountChartFromResult(container, result) {
    // Chart title is always "Median Index Price (N runs)" regardless of
    // context. The surrounding panel heading (e.g. "Data Used for
    // Comparison") carries that context instead.
    const medianPrices = result.medianPriceByMonth();
    const { declineSegments, rallySegments } = findSustainedTrends(medianPrices);
    return mountPriceChart(
      container,
      {
        sampleSeries: result.priceSeriesUsed,
        median: medianPrices,
        declineSegments,
        rallySegments,
        numRuns: result.numRuns,
      },
      { yScale: state.chartScale }
    );
  }

  function renderInvestingResults(result, strategyName, strategyDescription) {
    state.lastSingleResult = { result, name: strategyName, description: strategyDescription };

    el.chartPlaceholder.hidden = true;
    el.chartHost.hidden = false;
    if (state.chartController) {
      state.chartController.destroy();
      state.chartController = null;
    }
    state.chartController = mountChartFromResult(el.chartHost, result);

    renderStatsCard(strategyName, strategyDescription, result);
  }

  function renderStatsCard(strategyName, strategyDescription, result) {
    el.outputInitial.hidden = true;
    el.compareContent.hidden = true;
    el.outputContent.hidden = false;
    el.outputContent.innerHTML = "";

    const card = document.createElement("div");
    card.className = "card";

    const title = document.createElement("h1");
    title.className = "panel-title";
    title.textContent = "Output";
    card.appendChild(title);

    const nameEl = document.createElement("p");
    nameEl.className = "result-name";
    nameEl.textContent = strategyName;
    card.appendChild(nameEl);

    if (strategyDescription) {
      const descEl = document.createElement("p");
      descEl.className = "result-desc";
      descEl.textContent = strategyDescription;
      card.appendChild(descEl);
    }

    for (const [groupTitle, rows] of summaryGroups(result)) {
      const hr = document.createElement("hr");
      hr.className = "sep";
      card.appendChild(hr);
      const h = document.createElement("div");
      h.className = "stat-group-title";
      h.textContent = groupTitle;
      card.appendChild(h);

      for (const [label, value, raw] of rows) {
        const row = document.createElement("div");
        row.className = "stat-row";
        const labelEl = document.createElement("span");
        labelEl.textContent = label;
        row.appendChild(labelEl);

        if (Array.isArray(raw)) {
          const [lowRaw, highRaw] = raw;
          const valueEl = document.createElement("span");
          valueEl.className = "value";
          valueEl.innerHTML =
            `<span class="lo">${lowRaw.toFixed(1)}%</span> to <span class="hi">${highRaw.toFixed(1)}%</span>`;
          row.appendChild(valueEl);
        } else {
          const valueEl = document.createElement("span");
          valueEl.className = "value";
          if (raw !== null) valueEl.classList.add(raw >= 0 ? "positive" : "negative");
          valueEl.textContent = value;
          row.appendChild(valueEl);
        }
        card.appendChild(row);
      }
    }

    el.outputContent.appendChild(card);
  }
})();
