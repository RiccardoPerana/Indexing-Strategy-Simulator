/*
 * theme.js
 *
 * Colors that script sets directly: the canvas chart, which cannot read
 * CSS, and the Compare All rank highlights. Everything else is styled in
 * css/style.css; the chart values below are the same navy/cream hexes
 * the stylesheet's custom properties use.
 */

const Theme = Object.freeze({
  CHART_BG: "#06162B",
  CHART_TEXT: "#F2E9D8",
  CHART_GRID: "#1D4D7A",
  CHART_MEDIAN_LINE: "#8FB3C7",
  CHART_DECLINE: "#A5443C",
  CHART_RALLY: "#3C7A5C",
  CHART_SAMPLE_RUNS: "#7C8B99",

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
