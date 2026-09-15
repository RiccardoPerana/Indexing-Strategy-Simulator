/*
 * theme.js
 *
 * The navy/cream color palette -- kept as the single source of truth for
 * both the page chrome (css/style.css uses the same hex values) and the
 * canvas chart, so nothing drifts between them.
 */

const Theme = Object.freeze({
  BG_DARKEST: "#06162B",
  BG_CARD: "#0B2A4A",
  ACCENT_PRIMARY: "#1D4D7A",
  ACCENT_MUTED: "#8FB3C7",
  TEXT_CREAM: "#F2E9D8",

  ACCENT_SUCCESS: "#3C7A5C",
  ACCENT_WARNING: "#B8912E",
  ACCENT_DANGER: "#A5443C",
  ACCENT_LIGHT: "#35566E",

  OUTPUT_POSITIVE: "#C1E1C1",
  OUTPUT_NEGATIVE: "#FAA0A0",

  CHART_BG: "#06162B",
  CHART_TEXT: "#F2E9D8",
  CHART_GRID: "#1D4D7A",
  CHART_MEDIAN_LINE: "#8FB3C7",
  CHART_DECLINE: "#A5443C",
  CHART_RALLY: "#3C7A5C",
  CHART_SAMPLE_RUNS: "#7C8B99",

  COMPARE_BUTTON: "#ff964f",
  SWITCH_GRAPH_BUTTON: "#CCCCC4",

  RANK_GREEN_1ST: "#91CA91",
  RANK_GREEN_2ND: "#B0D9B0",
  RANK_GREEN_3RD: "#C1E1C1",
  RANK_RED_3RD_LAST: "#FBBBBB",
  RANK_RED_2ND_LAST: "#FAA0A0",
  RANK_RED_LAST: "#F76464",
});

// 0-indexed rank (0 = best) out of `total` items -> highlight color, or
// null outside the top-3/bottom-3. Top-3 checks come first so with fewer
// than 6 items a rank gets its TOP color, not both.
function getRankColor(rank, total) {
  if (rank === 0) return Theme.RANK_GREEN_1ST;
  if (rank === 1) return Theme.RANK_GREEN_2ND;
  if (rank === 2) return Theme.RANK_GREEN_3RD;
  if (rank === total - 1) return Theme.RANK_RED_LAST;
  if (rank === total - 2) return Theme.RANK_RED_2ND_LAST;
  if (rank === total - 3) return Theme.RANK_RED_3RD_LAST;
  return null;
}
