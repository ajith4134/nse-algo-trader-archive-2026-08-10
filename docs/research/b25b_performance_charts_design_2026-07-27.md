# B25b — first real charts on the dashboard (performance card)

Operator: *"i do not see any difference in the dash board"* — a fair verdict. Today's work was
behaviour (option orders truncated to zero, scanner deadlocked, entry gates halting everything), and
the only visual deltas were three columns that render **per open position** (invisible with the
market closed and 0 open) plus three rows buried in a 70-row coverage list.

This slice adds the thing the dashboard has never had: **charts**.

**Sourcing note (Rule I):** no OSS charting library. The page is a single self-contained HTML
template with no build step and no external requests; adding a chart library would mean either a CDN
(the page must work offline on a phone) or a bundler (there is no build pipeline). Both charts here
are ~40 lines of inline SVG over data the snapshot already carries. If charting needs later grow
past this — zoom, brushing, many series — revisit and source a real library then.

## Dataviz procedure (followed in order, colour LAST)

**1 · Form.** Two jobs, two forms:
- *Cumulative net P&L across closed trades* — change-over-time → **line with a zero baseline**. This
  is the single most important thing a trader looks at and the dashboard has never shown it.
- *Capture ratio by mechanism* — magnitude with **polarity** (negative = gives profit back, positive
  = keeps it) → **diverging horizontal bars**, zero-anchored.

**2 · Colour by job.** The equity line is ONE series → no legend (the title names it), drawn in
categorical slot 1. Capture is polar → the **diverging pair** blue↔red with a neutral gray midpoint,
never a categorical hue per bar.

**3 · Validated, not eyeballed** (`scripts/validate_palette.js`):
- light categorical `#2a78d6,#eb6834,#1baf7a,#eda100` → ALL PASS (one contrast WARN on aqua/yellow →
  obligates visible labels; the bars are directly labelled, which discharges it)
- dark categorical `#3987e5,#d95926,#199e70,#c98500` → ALL PASS
- diverging poles `#2a78d6 ↔ #d03b3b` → ALL PASS, worst adjacent ΔE **23.8 protan / 31.6 normal**

**4 · Marks.** 2px line; 4px rounded bar ends anchored to the zero baseline; recessive 1px grid;
2px surface gap between adjacent bars; direct value labels on every bar (few enough that this is not
label spam) and on the equity end-point only.

**5 · Hover.** Per-bar tooltip on capture; crosshair + tooltip on the equity line.

**6 · Accessibility.** Single-series equity → no legend box. Capture bars carry a direct numeric
label, so identity is never colour-alone. Both charts sit above a table view of the same numbers
(the closed-trades table and the exit-efficiency panel already exist). Dark mode uses the palette's
own dark steps under BOTH `prefers-color-scheme` and `[data-theme]`, not an automatic flip.

**7 · Render and look** — screenshot the page and eyeball for collisions/overflow before signing off.

## Data contract (backend part)

The capture numbers currently exist only as formatted metric STRINGS on the `exit_efficiency`
surface, which cannot be charted. So the snapshot gains a structured
`exit_efficiency_rows: [{mechanism_name, capture_ratio, mean_realized_pnl,
mean_maximum_favourable_profit, measured_count}]`, from the read
`exit_efficiency_by_mechanism()` that B23c already built. The equity curve needs no new data —
`closed_trades` already carries `realized_pnl`, `total_fees` and `closed_at`.

**Net, not gross.** The equity curve plots `realized_pnl - total_fees` cumulatively. Plotting gross
would be the same lie B28 was built to stop.

## Acceptance criteria

1. Cumulative **net** P&L renders as a line with a visible zero baseline; the end value matches
   `sum(realized_pnl) - sum(total_fees)` over the plotted trades.
2. Capture bars are zero-anchored and diverge by sign; a negative bar is visually opposite a positive one.
3. Every bar carries a direct numeric label (discharges the contrast WARN and the colour-alone rule).
4. Both charts render in light AND dark using the validated steps.
5. Charts degrade gracefully to an explicit empty state with no data — never a broken axis.
6. No external network request (the page stays self-contained and phone-usable offline).

## NOT in this slice (Rule K)

Grouping/filtering the 70-row feature-coverage list, per-feature drill-down, and any layout
restructure — those are the rest of B25b and are logged as remaining.
