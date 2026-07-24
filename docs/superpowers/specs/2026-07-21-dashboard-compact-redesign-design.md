# Dashboard Compact Redesign

**Date:** 2026-07-21
**Status:** Approved

## Problem

The managed README dashboard section (`render_dashboard` in
`src/tomax/render/markdown.py`) has grown hard to scan:

1. The Skills/MCP horizontal bar chart grows with the number of distinct
   names observed. With 24 skills observed in practice, the chart is
   926px tall (`max(260, rows * 34 + 110)`), dwarfing every other chart
   in the dashboard and forcing a lot of scrolling.
2. There's no way to see, at a glance, how usage is split across the
   three supported agents (Hermes, Claude Code, Codex).
3. The markdown scaffolding repeats itself: every chart gets its own H3
   heading (`### Skills`, `### Rolling 14 Days Activity`, ...) even
   though the PNG already renders that exact text as its in-chart title.
   Each redundant heading adds real, unnecessary vertical space when
   GitHub renders the README.

## Goals

- Cap the height of the Skills/MCP charts regardless of how many
  distinct names are observed.
- Add an agent usage-share visualization (Hermes / Claude Code / Codex),
  by lifetime token share.
- Reduce total rendered height of the managed dashboard section.
- Keep the change pure-Python/Plotly, consistent with the existing
  chart-rendering approach (static PNG via Kaleido, no client-side JS).

## Non-goals

- Changing what data is collected or how it's aggregated
  (`aggregate.py` is unaffected beyond reading `lifetime_summary["agents"]`,
  which already exists).
- Adding a rolling-window (14-day) variant of the agent-share bar — this
  iteration is lifetime-only, matching the existing "Total Activity"
  scope.
- Making Rolling/Total token charts side-by-side (out of scope per
  discussion; only their height shrinks).

## Design

### 1. Skills/MCP: bar chart → pie chart, with a top-N cap

`render_usage_bar_chart` in `src/tomax/render/plotly.py` is
replaced by `render_usage_pie_chart(*, title: str, counters: Mapping[str, int], top_n: int) -> bytes`.

Behavior:
- Reuse the existing `rank_usage()` helper to sort counters descending
  (ties broken alphabetically, as today).
- Keep the top `top_n` entries as individual pie slices.
- If more than `top_n` entries exist, sum the remainder into a single
  `"Other"` slice appended last.
- Empty-counters case keeps today's "No {skill,mcp} activity observed
  yet." annotation, same as the current bar chart's empty state.
- Chart is a fixed size regardless of `top_n` or category count —
  this is what caps the height problem. Target ~460px wide × ~340px
  tall (legend below or beside the circle; exact Plotly legend
  placement decided during implementation, but must not grow with
  category count).

`top_n` is caller-supplied, not hardcoded, so it can be controlled via
CLI (see "CLI/config plumbing" below). Default: **6**.

Skills and MCP share a single `top_n` value — one CLI flag, not two —
since both can have a long tail (this session alone used 9 distinct MCP
tools).

### 2. New chart: agent usage-share bar

New function `render_agent_share_bar(*, agent_totals: Mapping[str, dict]) -> bytes`
in `src/tomax/render/plotly.py`.

- Single 100%-stacked horizontal bar (one row, one segment per agent).
- Segment width = that agent's share of total lifetime `headline_total`
  tokens across all three agents (`SupportedAgent.HERMES_AGENT`,
  `CLAUDE_CODE`, `CODEX` — matches `lifetime_summary["agents"]` from
  `aggregate_records`).
- Segment order is fixed (Hermes → Claude Code → Codex), not sorted by
  size, so color-to-agent association stays stable across renders.
- Each segment labeled with its percentage.
- Colors use each product's brand color for recognizability:
  - Hermes: `#f59e0b`
  - Claude Code: `#d97757`
  - Codex: `#10a37f`
- If total tokens across all agents is 0, render the same "No activity
  observed yet." empty state pattern used elsewhere.
- Compact: ~150px tall, full 960px wide (matches existing line charts'
  width).

### 3. Markdown layout: drop redundant headings, add side-by-side pies

`render_dashboard_markdown` in `src/tomax/render/markdown.py`
changes from:

```
## Token Usage
### Rolling 14 Days Activity
![...](rolling)
## Total Activity
![...](total)
## Skill/MCP Usage
### Skills
![...](skills)
### MCP
![...](mcp)
```

to:

```
## Token Usage
![Rolling 14 Days Activity](rolling)
![Total Activity](total)

## Agent Share
![Agent Share](agent-share)

## Skill / MCP Usage
| ![Skills](skills) | ![MCP](mcp) |
|---|---|
```

Rationale: every dropped H3 duplicated text the PNG title already
shows. This also fixes a pre-existing heading-hierarchy inconsistency
(`## Total Activity` was a sibling of `## Token Usage` rather than
nested under it, despite being logically part of "Token Usage").

Skills/MCP go side by side via a plain 2-column markdown table (no raw
HTML), matching the project's existing plain-markdown style.

### 4. Sizing changes to existing charts

In `src/tomax/render/plotly.py`:
- `_TOKEN_CHART_HEIGHT`: 390 → 300
- Pie chart margins trimmed relative to the old bar chart's margins
  (a pie doesn't need the bar chart's long axis-label margin).

### 5. CLI/config plumbing for `--pie-top-n`

`top_n` flows from two entry points down to `render_usage_pie_chart`,
both defaulting to **6**:

- **`tomax render`** (`src/tomax/cli.py`): new
  `--pie-top-n` typer option → `commands/render.py: render(..., pie_top_n: int = 6)`
  → `render_dashboard(..., pie_top_n=...)`.
- **`scripts/build_profile_dashboard.py`** (runs in the profile repo's
  GitHub Action): new `--pie-top-n` argparse option, same default,
  threaded through `build(..., pie_top_n: int = 6)` →
  `render_dashboard(..., pie_top_n=...)`.

`render_dashboard()` and `render_dashboard_markdown()` in
`render/markdown.py` gain:
- `pie_top_n: int = 6` param on `render_dashboard` (used when calling
  `render_usage_pie_chart` for both Skills and MCP).
- `agent_share_chart_path` param (default
  `"assets/tomax/agent-share.png"`) on both functions, alongside
  the existing four chart-path params.

`templates/github-workflow.yml` is unaffected — it will pick up the
new default `--pie-top-n 6` behavior automatically without edits; a
future iteration could expose it as a workflow input, but that's out
of scope here.

## Affected files (implementation reference, not exhaustive)

- `src/tomax/render/plotly.py` — pie chart fn, agent-share bar fn, sizing constants
- `src/tomax/render/markdown.py` — markdown layout, `render_dashboard` signature
- `src/tomax/commands/render.py` — thread `pie_top_n` through local preview
- `src/tomax/cli.py` — `--pie-top-n` typer option
- `scripts/build_profile_dashboard.py` — `--pie-top-n` argparse option
- `tests/render/test_markdown.py`, plotly render tests — update for new chart fns/layout

## Testing

- Unit tests for `render_usage_pie_chart`: top-N cap produces an
  "Other" slice with correct summed value; counters ≤ top_n produce no
  "Other" slice; empty counters produce the empty-state chart.
- Unit tests for `render_agent_share_bar`: percentages sum to 100
  (rounding-safe); fixed segment order; all-zero produces empty state.
- `render_dashboard_markdown` snapshot/string test for the new layout
  and the agent-share chart path.
- Existing `render_dashboard` integration test updated for the new
  `charts` dict key (`"agent_share"`) and new markdown shape.
