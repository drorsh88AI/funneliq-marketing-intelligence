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
//   - 12A, 27.09.2026 (tester finding O3: "לא ברור מה הגרף אמור
//     להציג, למה הכותרת באנגלית"; overturns S11/P11A-D7): chart
//     chrome (title, axis names, per-bar category labels) is now
//     Hebrew, matching the accessible fallback table below it. Only
//     the chart's own title keeps a small English subtitle line
//     (the original term, for anyone cross-referencing code/exports).
//     The SVG itself stays aria-hidden -- decorative, not a second
//     accessible surface -- this only changes what the decoration
//     itself says.
//   - up to five semantic colors -- this bar-chart variant uses one
//     (--color-primary, per tokens.css's own comment: "The Overview
//     conversion chart uses --color-primary as its bar fill").

const SVG_NS = "http://www.w3.org/2000/svg";
const VIEW_WIDTH = 400;
const VIEW_HEIGHT = 225; // 16:9
// top grew again, 28->36 (12A): room for a second, smaller title line
// (the English subtitle) under the Hebrew main title -- bottom/left
// unchanged from P11A-D7 (an X-axis name below the per-bar tick
// labels, a rotated Y-axis name to its left).
const PADDING = { top: 36, right: 16, bottom: 44, left: 28 };

/** data: [{ xHebrew, xEnglish, value, lower?, upper? }]. `value` may be
 * null -- rendered as a labeled "אין נתונים" gap, never a 0-height bar
 * (IA.md:112: conversion_rate null -> N/A, ⛔ never a zero column; that
 * rule is about the VALUE, and a chart silently drawing a real 0-height
 * bar for a missing value violates it just as much as the table would).
 * `lower`/`upper`, when given on ANY row, draw a whisker (a vertical
 * range line + caps) over that bar -- DESIGN.md §4's own shared rule
 * for all four live charts: "טווחי אי-ודאות ב-whisker עם מקרא
 * טקסטואלי". `legend`, when given, renders that textual legend as a
 * caption paragraph under the chart -- this is the "מקרא טקסטואלי"
 * itself, never a second color-coded visual legend.
 *
 * 12A, 27.09.2026 (overturns P11A-D7/S11 for chart chrome -- tester
 * finding O3): `title` is the chart's own Hebrew title, rendered
 * INSIDE the aria-hidden SVG; `titleEnglish` becomes a small subtitle
 * line under it, ⛔ no longer the only title. `xLabel`/`yLabel` (also
 * used by the accessible fallback table's headers, per this module's
 * pre-existing convention) now render the axis names too -- the
 * `xLabelEnglish`/`yLabelEnglish` params this checkpoint removes had
 * no other purpose. Per-bar category ticks read `d.xHebrew` (`xEnglish`
 * stays on each data row for callers that still find it useful
 * elsewhere; the SVG itself no longer reads it). A caller passing a
 * `legend` writes it in Hebrew now, matching everything else here. */
// `extraColumn` (12A, 27.09.2026): optional `{ label, formatValue(d) }`,
// inserts one more Hebrew-headed column into the fallback table,
// BETWEEN the row header (xHebrew) and the value column -- for a
// caller whose data carries more than one number per category (e.g.
// Overview's n_records alongside conversion_rate). Still ONE fallback
// table for the chart, not a second one: the mandatory rule above
// ("תמיד מרנדר את שניהם יחד") is about the chart never shipping
// without ITS OWN fallback, not about how many columns that table has.
// Undefined by default -- every existing caller (budget.js,
// followup.js) is unaffected.
// `midCaptions` (12A, 28.09.2026, Overview O2/O4 DOM-order fix):
// optional string[], each rendered as its own `<p class="screen-intro">`
// (the last one also gets `screen-intro-end`) and inserted INSIDE this
// same .chart-live wrapper, between the SVG and the fallback table --
// for a caller (Overview) whose explanatory text belongs between the
// chart and its accessible table, without splitting the component into
// two separately-returned nodes: renderBarChart() always returns ONE
// .chart-live element containing the SVG and the fallback table,
// exactly like every other caller (budget.js, followup.js). Undefined
// by default -- those two callers are unaffected.
export function renderBarChart({ data, xLabel, yLabel, title, titleEnglish, formatValue, legend, extraColumn, barClassName = "chart-bar", midCaptions }) {
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

  // 12A: Hebrew main title + a small English subtitle under it,
  // inside the SVG. Two separate <text> elements, not two tspans on
  // one, so the subtitle's own smaller class fully controls its size.
  const titleEl = document.createElementNS(SVG_NS, "text");
  titleEl.setAttribute("x", String(VIEW_WIDTH / 2));
  titleEl.setAttribute("y", "13");
  titleEl.setAttribute("text-anchor", "middle");
  titleEl.setAttribute("class", "chart-title");
  titleEl.textContent = title;
  svg.appendChild(titleEl);

  const subtitleEl = document.createElementNS(SVG_NS, "text");
  subtitleEl.setAttribute("x", String(VIEW_WIDTH / 2));
  subtitleEl.setAttribute("y", "24");
  subtitleEl.setAttribute("text-anchor", "middle");
  subtitleEl.setAttribute("class", "chart-title-subtitle");
  subtitleEl.textContent = titleEnglish;
  svg.appendChild(subtitleEl);

  // Axis names: Hebrew (xLabel/yLabel), same strings the accessible
  // fallback table's own headers already use below.
  const xAxisName = document.createElementNS(SVG_NS, "text");
  xAxisName.setAttribute("x", String(VIEW_WIDTH / 2));
  xAxisName.setAttribute("y", String(VIEW_HEIGHT - 6));
  xAxisName.setAttribute("text-anchor", "middle");
  xAxisName.setAttribute("class", "chart-axis-name");
  xAxisName.textContent = xLabel;
  svg.appendChild(xAxisName);

  const yAxisName = document.createElementNS(SVG_NS, "text");
  yAxisName.setAttribute("x", "11");
  yAxisName.setAttribute("y", String(PADDING.top + plotHeight / 2));
  yAxisName.setAttribute("text-anchor", "middle");
  yAxisName.setAttribute("class", "chart-axis-name");
  yAxisName.setAttribute("transform", `rotate(-90 11 ${PADDING.top + plotHeight / 2})`);
  yAxisName.textContent = yLabel;
  svg.appendChild(yAxisName);

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
    const x = PADDING.left + i * (barWidth + barGap);
    const hasValue = typeof d.value === "number";

    if (hasValue) {
      const barHeight = (d.value / chartMax) * plotHeight;
      const y = PADDING.top + plotHeight - barHeight;
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", String(x));
      rect.setAttribute("y", String(y));
      rect.setAttribute("width", String(barWidth));
      rect.setAttribute("height", String(Math.max(barHeight, 0)));
      rect.setAttribute("class", barClassName);
      svg.appendChild(rect);
    } else {
      // 12A (IA.md:112, tester finding "null נראה כאפס בגרף"): no bar
      // at all for a missing value -- drawing one at height 0 would be
      // visually indistinguishable from a real 0%, exactly what the
      // table's own "N/A, never a zero column" rule already forbids.
      // A short baseline dash + "N/A" label mark the category as
      // present with no data, not silently absent and not zero.
      const dash = document.createElementNS(SVG_NS, "line");
      dash.setAttribute("x1", String(x + barWidth * 0.3));
      dash.setAttribute("x2", String(x + barWidth * 0.7));
      dash.setAttribute("y1", String(PADDING.top + plotHeight));
      dash.setAttribute("y2", String(PADDING.top + plotHeight));
      dash.setAttribute("class", "chart-bar-missing");
      svg.appendChild(dash);

      const naLabel = document.createElementNS(SVG_NS, "text");
      naLabel.setAttribute("x", String(x + barWidth / 2));
      naLabel.setAttribute("y", String(PADDING.top + plotHeight - 4));
      naLabel.setAttribute("text-anchor", "middle");
      naLabel.setAttribute("class", "chart-bar-missing-label");
      naLabel.textContent = "N/A";
      svg.appendChild(naLabel);
    }

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", String(x + barWidth / 2));
    label.setAttribute("y", String(VIEW_HEIGHT - PADDING.bottom + 16));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "chart-axis-label");
    label.textContent = d.xHebrew;
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

  if (midCaptions && midCaptions.length) {
    midCaptions.forEach((text, i) => {
      const p = document.createElement("p");
      p.className = i === midCaptions.length - 1 ? "screen-intro screen-intro-end" : "screen-intro";
      p.textContent = text;
      wrapper.appendChild(p);
    });
  }

  // Accessible fallback table -- part of the SAME component, always
  // rendered alongside the SVG (own overflow-x container, DESIGN.md
  // §4.1: "לעולם לא גלילת גוף העמוד").
  const tableWrap = document.createElement("div");
  tableWrap.className = "chart-fallback-table";
  const table = document.createElement("table");

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  const headings = extraColumn ? [xLabel, extraColumn.label, yLabel] : [xLabel, yLabel];
  for (const heading of headings) {
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
    if (extraColumn) {
      const extraCell = document.createElement("td");
      extraCell.textContent = extraColumn.formatValue(d);
      row.appendChild(extraCell);
    }
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
