"use strict";

// FunnelIQ chart-live primitive (phase 11, checkpoint 3, DESIGN.md §4).
// Manual SVG -- no charting library. Every chart-live instance renders
// BOTH the SVG and an accessible fallback table TOGETHER (DESIGN.md:
// "fallback טבלאי נגיש לכל גרף חי -- חובה, לא אופציונלי... chart-live
// תמיד מרנדר את שניהם יחד") -- never one without the other, never a
// toggle between them.
//
// Rules enforced here (DESIGN.md §4, §4.1):
//   - bars start at 0, never a truncated y-axis.
//   - viewBox-based SVG, no hardcoded pixel width/height -- responsive,
//     16:9 aspect ratio (Desktop, §4.1); CSS gives it width:100%.
//   - a subtle grid.
//   - chart chrome (axis tick labels) in English -- the SVG is
//     aria-hidden and decorative; the table below is the actual
//     accessible content, so its own headers/row labels are in
//     Hebrew, matching the rest of the UI (DESIGN.md's "כותרות/צירים/
//     מקרא באנגלית" rule governs the SVG's own chrome, not this
//     separately-named accessible fallback).
//   - up to five semantic colors -- this bar-chart variant uses one
//     (--color-primary, per tokens.css's own comment: "The Overview
//     conversion chart uses --color-primary as its bar fill").

const SVG_NS = "http://www.w3.org/2000/svg";
const VIEW_WIDTH = 400;
const VIEW_HEIGHT = 225; // 16:9
const PADDING = { top: 16, right: 16, bottom: 32, left: 16 };

/** data: [{ xHebrew, xEnglish, value, lower?, upper? }], value may be
 * null (N/A -- 0-height bar). `lower`/`upper`, when given on ANY row,
 * draw a whisker (a vertical range line + caps) over that bar --
 * DESIGN.md §4's own shared rule for all four live charts: "טווחי
 * אי-ודאות ב-whisker עם מקרא טקסטואלי". `legend`, when given, renders
 * that textual legend as a caption paragraph under the chart -- this is
 * the "מקרא טקסטואלי" itself, never a second color-coded visual legend. */
export function renderBarChart({ data, xLabel, yLabel, formatValue, legend, barClassName = "chart-bar" }) {
  const wrapper = document.createElement("div");
  wrapper.className = "chart-live";

  const numericValues = data.map((d) => d.value).filter((v) => typeof v === "number");
  const whiskerValues = data.flatMap((d) => [d.lower, d.upper]).filter((v) => typeof v === "number");
  const max = Math.max(0, ...numericValues, ...whiskerValues);
  const chartMax = max > 0 ? max : 1; // avoid a degenerate 0-height chart

  const plotWidth = VIEW_WIDTH - PADDING.left - PADDING.right;
  const plotHeight = VIEW_HEIGHT - PADDING.top - PADDING.bottom;
  const barGap = 12;
  const barWidth = (plotWidth - barGap * (data.length - 1)) / data.length;

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-hidden", "true"); // the table below is the accessible equivalent
  svg.classList.add("chart-live-svg");

  const GRID_LINES = 4;
  for (let i = 0; i <= GRID_LINES; i++) {
    const y = PADDING.top + (plotHeight * i) / GRID_LINES;
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", String(PADDING.left));
    line.setAttribute("x2", String(VIEW_WIDTH - PADDING.right));
    line.setAttribute("y1", String(y));
    line.setAttribute("y2", String(y));
    line.setAttribute("class", "chart-grid-line");
    svg.appendChild(line);
  }

  data.forEach((d, i) => {
    const value = typeof d.value === "number" ? d.value : 0;
    const barHeight = (value / chartMax) * plotHeight;
    const x = PADDING.left + i * (barWidth + barGap);
    const y = PADDING.top + plotHeight - barHeight;

    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", String(x));
    rect.setAttribute("y", String(y));
    rect.setAttribute("width", String(barWidth));
    rect.setAttribute("height", String(Math.max(barHeight, 0)));
    rect.setAttribute("class", barClassName);
    svg.appendChild(rect);

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", String(x + barWidth / 2));
    label.setAttribute("y", String(VIEW_HEIGHT - PADDING.bottom + 16));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "chart-axis-label");
    label.textContent = d.xEnglish;
    svg.appendChild(label);

    if (typeof d.lower === "number" && typeof d.upper === "number") {
      const centerX = x + barWidth / 2;
      const yLower = PADDING.top + plotHeight - (d.lower / chartMax) * plotHeight;
      const yUpper = PADDING.top + plotHeight - (d.upper / chartMax) * plotHeight;
      const capHalfWidth = Math.min(barWidth / 4, 10);

      const whiskerLine = document.createElementNS(SVG_NS, "line");
      whiskerLine.setAttribute("x1", String(centerX));
      whiskerLine.setAttribute("x2", String(centerX));
      whiskerLine.setAttribute("y1", String(yUpper));
      whiskerLine.setAttribute("y2", String(yLower));
      whiskerLine.setAttribute("class", "chart-whisker-line");
      svg.appendChild(whiskerLine);

      for (const yCap of [yLower, yUpper]) {
        const cap = document.createElementNS(SVG_NS, "line");
        cap.setAttribute("x1", String(centerX - capHalfWidth));
        cap.setAttribute("x2", String(centerX + capHalfWidth));
        cap.setAttribute("y1", String(yCap));
        cap.setAttribute("y2", String(yCap));
        cap.setAttribute("class", "chart-whisker-cap");
        svg.appendChild(cap);
      }
    }
  });

  wrapper.appendChild(svg);

  // Accessible fallback table -- part of the SAME component, always
  // rendered alongside the SVG (own overflow-x container, DESIGN.md
  // §4.1: "לעולם לא גלילת גוף העמוד").
  const tableWrap = document.createElement("div");
  tableWrap.className = "chart-fallback-table";
  const table = document.createElement("table");

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const heading of [xLabel, yLabel]) {
    const th = document.createElement("th");
    th.textContent = heading;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const d of data) {
    const row = document.createElement("tr");
    const rowHeader = document.createElement("th");
    rowHeader.setAttribute("scope", "row");
    rowHeader.textContent = d.xHebrew;
    row.appendChild(rowHeader);
    const cell = document.createElement("td");
    cell.textContent = formatValue ? formatValue(d.value, d) : String(d.value ?? "");
    row.appendChild(cell);
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  wrapper.appendChild(tableWrap);

  if (legend) {
    const legendEl = document.createElement("p");
    legendEl.className = "chart-legend";
    legendEl.textContent = legend;
    wrapper.appendChild(legendEl);
  }

  return wrapper;
}
