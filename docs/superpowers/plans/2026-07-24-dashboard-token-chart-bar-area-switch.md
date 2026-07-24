# Bar/Area switch for total token usage chart

## Context

Total token usage chart currently always renders as an area chart (`dashboard-ui/src/charts/TokenArea.tsx`), now showing full collected history. For long date ranges an area chart gets visually noisy; user wants a **stacked bar chart per date** once the span exceeds a configurable day threshold (default 15 days). `BarChart`/`Bar`/`BarXAxis` aren't hand-rolled — they come from the same `@bklit` shadcn-style registry (`ui.bklit.com`, configured in `dashboard-ui/components.json`) that the existing `AreaChart`/`Area`/`XAxis` components were already installed from. Confirmed via `pnpm dlx shadcn@latest add @bklit/bar-chart --dry-run`: adds 10 new files (`bar-chart.tsx`, `bar.tsx`, `bar-x-axis.tsx`, `bar-y-axis.tsx`, `bar-squares*.ts`, `bar-depth-geometry.ts`, `bar-chart-loading.tsx`), 12 already-present deps, 47 already-present CSS vars, and **overwrites `chart-formatters.ts`** with the registry's stock version — which would silently drop this project's locale customization (`getLocale()`-driven `Intl` formatters), `windowDateFmt`, and `parseISODate` (all used by `App.tsx`). That overwrite must be reconciled by hand right after running the installer.

## Part 1 — Install bar chart primitives via the bklit registry

1. `cd dashboard-ui && pnpm dlx shadcn@latest add @bklit/bar-chart` (no `--dry-run`).
2. Immediately fix `src/components/charts/chart-formatters.ts`: re-diff against git, restore the locale-aware `getLocale()` import/usage on `shortDateFmt`/`weekdayDateFmt`/`hmsTimeFmt`/`intFmt`, and restore the `windowDateFmt` export and `parseISODate` function the registry's version dropped — while keeping any genuinely new content the registry added (diff first with `git diff src/components/charts/chart-formatters.ts` to see exactly what's new vs. dropped).
3. `git diff --stat` to confirm no other unexpected overwrites beyond what the dry-run reported.

## Part 2 — Token chart type switch (dashboard-ui)

- **`dashboard-ui/src/charts/TokenBar.tsx`** (new, mirrors `TokenArea.tsx`): same `TokenPoint` shape/legend/tooltip pattern, using the installed `BarChart`/`Bar`/`BarXAxis` per the official stacked-bar pattern:
  ```tsx
  <BarChart data={data} xDataKey="date" aspectRatio="3 / 1" margin={{ left: 50 }} stacked stackGap={3}>
    <Grid horizontal />
    <Bar dataKey="input" fill={SERIES_COLORS.input} lineCap="butt" />
    <Bar dataKey="output" fill={SERIES_COLORS.output} lineCap="butt" />
    <Bar dataKey="reasoning" fill={SERIES_COLORS.reasoning} lineCap="butt" />
    <YAxis formatLargeNumbers />
    <BarXAxis />
    <ChartTooltip ... />  {/* same rows as TokenArea */}
  </BarChart>
  ```
  (`stacked` on `BarChart` + one `<Bar>` per series is the documented "stacked bars, multiple data sources" pattern — exactly what's needed for input/output/reasoning stacked per date.)
- **`dashboard-ui/src/charts/TokenChart.tsx`** (new): `export function TokenChart({ data, useBarChart }: { data: TokenPoint[]; useBarChart: boolean })` → renders `<TokenBar data={data} />` or `<TokenArea data={data} />`.
- **`dashboard-ui/src/App.tsx`**: add `tokensChartType: "bar" | "area"` to the `Data` type (~line 8-14); replace `<TokenArea data={data.tokens} />` (~line 42) with `<TokenChart data={data.tokens} useBarChart={data.tokensChartType === "bar"} />`.

## Part 3 — Threshold config (Python, persisted in AppConfig)

Follow the `initial_collection_start` pattern exactly (`src/tomax/config.py`):

- Add `bar_chart_threshold_days: int = 15` field to `AppConfig` (near line 71).
- Add `_validate_bar_chart_threshold_days(value)` validator (must be a positive int), called from `__post_init__`, mirroring `_validate_initial_collection_start`.
- Update `to_dict`/`from_dict` to include the field (lines ~97-113).
- New CLI subcommand `config_app.command("bar-chart-threshold")` in `cli.py` (mirrors `config_start_date` at `cli.py:84-106`): `tomax config bar-chart-threshold --days N`, validates `N >= 1` via `typer.BadParameter`, `replace(...)`, `save_config`.
- `doctor` command gets one more line: `typer.echo(f"bar chart threshold: {report.bar_chart_threshold_days} day(s)")`; `DoctorReport`/`run_doctor` in `doctor.py` gets the field plumbed through the same way `initial_collection_start` was.

## Part 4 — Thread threshold into dashboard_data.py, compute chart type server-side

Follow the exact `pie_top_n` thread (per-render display setting, sourced from persisted config instead of a flag):

- `src/tomax/commands/render.py` and `commands/dashboard.py`: load `config.bar_chart_threshold_days`, pass through to `dashboard/export.py`/`dashboard/payload.py` alongside existing `pie_top_n` threading (same call sites: `render.py:56,84`, `dashboard.py:31,47`, `dashboard/export.py:116,128`, `dashboard/payload.py:39,52`).
- `src/tomax/render/dashboard_data.py`: `build_dashboard_data(..., bar_chart_threshold_days: int = 15, ...)`. After computing `tokens`/`window` (lines ~37-54), compute span days from `window["start"]`/`window["end"]` (`date.fromisoformat(...)`, `(end - start).days + 1`) and add `"tokensChartType": "bar" if span_days > bar_chart_threshold_days else "area"` to the returned dict.

## Verification

- `pytest -q` — extend `tests/test_config.py` (threshold field default/validation/persistence), `tests/commands/test_cli.py` (`config bar-chart-threshold` command tests, mirroring `test_config_start_date_*`), `tests/commands/test_doctor.py` (surfaces threshold), `tests/render/test_dashboard_data.py` (asserts `tokensChartType` flips at the threshold boundary — exactly `threshold` days → `"area"`, `threshold + 1` days → `"bar"`).
- `cd dashboard-ui && pnpm build` (or existing build script) to confirm the newly-installed components + `TokenBar`/`TokenChart` type-check and compile.
- Manual: `tomax config bar-chart-threshold --days 5`, `tomax collect`, `tomax render --rebuild`, open the preview, confirm the chart renders as stacked bars when the collected span exceeds 5 days; bump `--days 100` and re-render to confirm it falls back to the area chart.
