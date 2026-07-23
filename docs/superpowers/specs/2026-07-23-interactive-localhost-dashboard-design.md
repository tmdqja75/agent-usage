# Interactive localhost dashboard — design

Date: 2026-07-23
Status: Approved (design), pending implementation plan

## Goal

Add a new CLI command that serves a **localhost interactive chart dashboard**
of agent usage. By default it uses this device's own local session data. With a
flag it aggregates multi-device session data published to the GitHub profile
repository. Charts are rendered with the [bklit](https://bklit.com) React
component library.

This is additive: the existing static Plotly PNG dashboard (for the GitHub
README) is unchanged. This feature is a separate, richer, interactive view.

## Non-goals (YAGNI)

- No static bundle export / `--output-dir`. Live server only.
- No hourly granularity (source records are per-UTC-day only).
- No auth, no remote hosting — strictly `localhost`.
- No change to the collector, ledger, publish, or existing render command.

## Architecture

Three layers. Both data sources converge on one chart-ready payload consumed by
one React UI.

### 1. Data builder — `src/agent_usage/render/dashboard_data.py` (new)

A pure function that turns validated daily payloads (the same
`validate_and_partition(...).valid_payloads` the Plotly path already produces)
into a single chart-ready `data.json` dict. No I/O, fully unit-testable.

Reuses `rank_usage` and `bucket_top_n`, which move from `render/plotly.py` into
a shared neutral helper module (`render/_counters.py`) imported by both. This
avoids the interactive path depending on the Plotly/Kaleido rendering module.

### 2. Data source — two paths, same builder

- **Default (local):** `LedgerRepository` → `stage_daily_records` →
  `validate_and_partition`. No Git, no network. Identical to the current
  `render` command's local staging.
- **`--all-devices`:** `git clone --depth 1 <config.repo_target>` into a temp
  dir → read `data/v1/devices/**` → `validate_and_partition` → aggregate across
  devices (existing `aggregate.py` logic) → same builder. Temp dir is removed
  afterward. Errors (no `repo_target` configured, clone failure) surface as
  clear CLI errors, not tracebacks.

### 3. Server — `src/agent_usage/dashboard/server.py` (new)

- stdlib `http.server` only (no new runtime Python dependency).
- Serves the committed `dashboard-ui/dist/` static assets.
- Serves `/data.json` from the in-memory payload built at startup.
- Binds `127.0.0.1` (never `0.0.0.0`), `--port` default 8000.
- Auto-opens the browser via `webbrowser` unless `--no-open`.
- Runs until Ctrl-C.

## UI — `dashboard-ui/` (Vite + React + bklit)

Committed to the repo: React **source** and the built **`dist/`**. End users
running the CLI need no Node; contributors editing charts need Node + pnpm.

### Theme (hard constraints)

- Page background: `#090A0B`.
- Each chart is contained in a block with background `#0E0F13`.
- **No colored/gradient backgrounds or gradient blocks anywhere.** The only
  permitted gradients are those internal to a bklit chart's own default design
  (e.g. an area-chart fill) — keep those intact.

### Layout / blocks

| Section | Chart | bklit component |
| --- | --- | --- |
| Total Token Usage | Area | area-chart |
| Usage by Agent (Hermes / Claude Code / Codex) | Ring | ring-chart |
| Skill usage | Pie w/ inner radius (donut) | pie-chart |
| MCP usage | Pie w/ inner radius (donut) | pie-chart |
| Activity | Calendar contribution heatmap | heatmap-chart (or custom grid in bklit dark style if the component doesn't fit) |

Skill and MCP donuts sit side by side in one row.

**Heatmap:** GitHub-contributions style. X axis = weeks, Y axis = day of week,
one cell per calendar day, cell intensity = **total** tokens that day (not split
by agent). Grayscale Less→More legend.

## `data.json` contract

```jsonc
{
  "window":  { "start": "2026-07-04", "end": "2026-07-18" },
  "tokens":  [ { "date": "2026-07-04", "input": 0, "output": 0, "reasoning": 0 } ],  // Area
  "agents":  [ { "agent": "claude_code", "tokens": 0 } ],                            // Ring
  "skills":  [ { "name": "brainstorming", "count": 0 } ],  // top-n + "Other"        // Donut
  "mcp":     [ { "name": "some-server", "count": 0 } ],    // top-n + "Other"        // Donut
  "heatmap": [ { "date": "2026-07-04", "tokens": 0 } ]                              // Calendar
}
```

- `agents` covers the three supported agents with display names resolved in the
  UI.
- `skills` / `mcp` use `bucket_top_n` with `--pie-top-n` (default 6), matching
  the existing Plotly behavior.
- `heatmap` is one entry per day in the window with the day's total tokens.

## CLI

New Typer command in `src/agent_usage/commands/dashboard.py`, wired in `cli.py`:

```
agent-usage dashboard [--all-devices] [--port 8000] [--no-open] [--pie-top-n 6]
```

## Testing

- **Data builder** (`dashboard_data.py`): pure-function unit tests over sample
  validated payloads — window, token series, agent totals, top-n bucketing,
  heatmap per-day totals, empty-data case.
- **Shared counters** (`_counters.py`): existing `rank_usage` / `bucket_top_n`
  tests move with them; Plotly tests still pass via re-export.
- **`--all-devices` fetch:** mock the `git clone` subprocess; assert it reads the
  cloned `data/v1/devices/**`, aggregates, and cleans up the temp dir; assert a
  clean error when `repo_target` is unset.
- **Server smoke:** start on an ephemeral port, assert `/` serves `dist`'s
  index and `/data.json` returns the built payload; bind is `127.0.0.1`.
- **UI `dist/` build is not run in CI** (no Node in the Python CI). The React
  source is committed; `dist/` is rebuilt and committed by hand when the UI
  changes.

## Open risk

`bklit`'s heatmap-chart may not natively do a GitHub-contributions calendar
layout. If it doesn't, build the calendar grid as a small custom component
styled to the bklit dark theme (still no gradients). Decide during
implementation; does not change the data contract.
