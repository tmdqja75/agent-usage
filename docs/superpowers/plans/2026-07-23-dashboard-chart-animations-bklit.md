# Dashboard chart animations via bklit components

## Context

The interactive dashboard (`dashboard-ui/`) currently renders charts with
hand-written visx components (`TokenArea`, `Donut`/`AgentRing`/`UsageDonut`,
`CalendarHeatmap`). They are static — no hover tooltips, no animated tickers,
no ring/pie hover motion. Goal: adopt bklit's official chart components for the
animated, interactive behavior:

1. **Area charts** — animated date ticker on hover + tooltip showing Input,
   Output, Reasoning token counts.
2. **Usage by Agent** — a real bklit **RingChart** (with legend), not a pie.
3. **Skills/MCP** — bklit **PieChart** where hovering offsets a slice from
   center and shows an animated value; center shows total usage when idle.

bklit is a shadcn-registry component set (built on visx + `motion` +
`@number-flow/react`). It requires shadcn/Tailwind wiring the current plain
Vite project lacks. This plan adds that wiring and swaps the three chart types
to bklit, keeping the existing `data.json` contract, the `#090A0B`/`#0E0F13`
theme, and the custom `CalendarHeatmap` (unchanged — heatmap not in scope).

**Gradient note:** the global no-gradient rule explicitly exempts gradients
internal to a bklit chart's own default rendering (e.g. Area fill). bklit's
Area gradient fill and the ring/pie glows are that exemption and are kept.
Page and block backgrounds stay flat hex fills.

## Approach

### 1. Bootstrap Tailwind v4 + shadcn in `dashboard-ui/`

- Add dev deps: `tailwindcss@^4`, `@tailwindcss/vite`, `tailwind-merge`, `clsx`.
  Add the `@tailwindcss/vite` plugin to `vite.config.ts`.
- Add path alias `@/*` → `src/*` in `tsconfig.json` and `vite.config.ts`
  (`resolve.alias`).
- Create `src/lib/utils.ts` exporting `cn()` (clsx + tailwind-merge) — the
  `@bklit/utils` registry dep expects this.
- Create `components.json` (shadcn config):
  - `tailwind.css` → `src/index.css`, `aliases.components` → `@/components`,
    `aliases.utils` → `@/lib/utils`, style `new-york`, `rsc: false`, `tsx: true`.
  - `registries: { "@bklit": "https://ui.bklit.com/r/{name}.json" }`.
- `src/index.css`: `@import "tailwindcss";` plus a `:root`/`@theme` block
  defining the chart tokens bklit reads: `--chart-1..5`,
  `--chart-line-primary`, `--chart-line-secondary`, `--chart-grid`, plus the
  shadcn base tokens (`--background`, `--foreground`, etc.). Keep
  `--page-bg: #090A0B` / `--block-bg: #0E0F13`. Fold the existing `theme.css`
  rules (`.dashboard`, `.block`, `.cal*`, `.legend`, `.empty`) in. Tailwind
  import first.

### 2. Install bklit components (shadcn CLI, non-interactive)

```
pnpm dlx shadcn@latest add @bklit/area-chart @bklit/ring-chart \
  @bklit/pie-chart @bklit/legend --yes --overwrite
```

Writes files under `src/components/charts/**`, installs npm deps
(`@visx/* @4.0.1-alpha.0`, `motion`, `@number-flow/react`, `d3-shape`,
`@base-ui/react`) and registry deps (`chart-context`, `chart-animation`,
`chart-series`, `grid`, `x-axis`, `chart-tooltip`, `shimmering-text`, `utils`,
`chart-utils`). Verify the CLI rewrote `@bklitui/ui/charts` imports to
`@/components/charts`. **Fallback if the CLI can't run non-interactively:**
fetch each `https://bklit.com/r/<name>.json`, write its `files[].content` to
the file's `target` path (rewriting `@bklitui/ui/charts` → `@/components/charts`),
and `pnpm add` the listed npm deps manually. (Registry payloads are real JSON;
`curl` output is mangled by the rtk hook in this environment — curl to a file
and read the file, or use `rtk proxy curl`.)

### 3. Rewrite the three chart components

Data still comes from `App.tsx`'s `fetch("data.json")`; only leaf components
change. Agent display-name map stays in `src/charts/names.ts`
(`hermes_agent`→Hermes, `claude_code`→Claude Code, `codex`→Codex).

- **`src/charts/TokenArea.tsx`** — replace visx `AreaStack` with:
  ```tsx
  <AreaChart data={points} xDataKey="date">
    <Grid horizontal />
    <Area dataKey="input"     fill="var(--chart-1)" />
    <Area dataKey="output"    fill="var(--chart-2)" />
    <Area dataKey="reasoning" fill="var(--chart-3)" />
    <XAxis />
    <ChartTooltip showDatePill rows={(p) => [
      { label: "Input", value: p.input },
      { label: "Output", value: p.output },
      { label: "Reasoning", value: p.reasoning },
    ]} />
  </AreaChart>
  ```
  Keep the empty-state guard. Convert `date` strings to `Date` if the installed
  `x-axis` requires it. "ALL area charts" = this one Area block (only area chart
  in the app). Satisfies requirement 1.

- **`src/charts/AgentRing.tsx`** — replace `Donut` with `RingChart` + `Legend`,
  controlled hover via `useState`:
  ```tsx
  const [hoveredIndex, setHoveredIndex] = useState<number|null>(null);
  const ringData = agents.filter(a=>a.tokens>0).map(a=>({
    label: agentLabel(a.agent), value: a.tokens, maxValue: totalTokens, color,
  }));
  <RingChart data={ringData} size={200}
    hoveredIndex={hoveredIndex} onHoverChange={setHoveredIndex}>
    {ringData.map((_,i)=><Ring key={i} index={i} />)}
    <RingCenter defaultLabel="Total tokens" />
  </RingChart>
  <Legend items={ringData} hoveredIndex={hoveredIndex}
          onHoverChange={setHoveredIndex}> marker/label/value(showPercentage)/progress </Legend>
  ```
  Satisfies requirement 2.

- **`src/charts/UsageDonut.tsx`** — replace shared `Donut` with `PieChart` +
  `PieSlice`, `innerRadius > 0` so `PieCenter` shows the total when idle;
  default `hoverEffect="translate"` offsets the hovered slice and `PieCenter`
  animates its value on hover:
  ```tsx
  <PieChart data={slices} size={220} innerRadius={64} padAngle={0.02}>
    {slices.map((_,i)=><PieSlice key={i} index={i} />)}
    <PieCenter defaultLabel="Total" />
  </PieChart>
  ```
  Used by both Skills and MCP blocks. Satisfies requirement 3.

- **`src/charts/Donut.tsx`** — delete (superseded). Drop `@visx/scale` /
  `d3-array` from `package.json` if nothing else uses them.
- **`src/charts/CalendarHeatmap.tsx`** and `names.ts` — keep. Extend palette in
  `names.ts` / tokens for ring/pie colors as needed.

### 4. Colors within the no-gradient rule

Slice/ring/series colors are flat hex via `--chart-*` tokens. Do **not** add
any `linear-gradient`/`radial-gradient` to page or block CSS. bklit's in-chart
Area gradient and glow filters are the permitted exception and stay at their
component defaults.

## Files

- Modify: `dashboard-ui/package.json`, `dashboard-ui/vite.config.ts`,
  `dashboard-ui/tsconfig.json`, `dashboard-ui/src/main.tsx` (import order),
  `dashboard-ui/src/theme.css` (fold into `index.css`).
- Create: `dashboard-ui/components.json`, `dashboard-ui/src/index.css`,
  `dashboard-ui/src/lib/utils.ts`, `dashboard-ui/src/components/charts/**`
  (bklit, generated).
- Rewrite: `dashboard-ui/src/charts/{TokenArea,AgentRing,UsageDonut}.tsx`.
- Delete: `dashboard-ui/src/charts/Donut.tsx`.
- `App.tsx` unchanged (same block structure and props).

No Python changes — `data.json` contract and server untouched.
`dashboard-ui/dist/` and `node_modules/` stay gitignored; `ui_build.py`
recompiles on demand.

## Verification

1. `cd dashboard-ui && pnpm install && pnpm build` → emits `dist/index.html`
   with no TypeScript/Vite errors.
2. `rm -rf dashboard-ui/dist && uv run tomax dashboard --no-open --port 8747`
   backgrounded; `curl -s http://127.0.0.1:8747/data.json` returns the payload;
   open the page and confirm:
   - Area block: hover shows animated date ticker + tooltip with Input /
     Output / Reasoning.
   - Usage by Agent: ring chart with legend; hover syncs ring ↔ legend.
   - Skills / MCP: hover pushes a slice out and animates its value; idle center
     shows the total count.
   - Page bg `#090A0B`, blocks `#0E0F13`, no gradient backgrounds (only bklit's
     in-chart Area gradient/glows).
3. `uv run pytest -q` still green (no Python touched; sanity check).
4. Commit on `feature/dashboard-compact-redesign`.

## Constraints (carry into implementation)

- Dashboard page background exactly `#090A0B`; each chart block exactly `#0E0F13`.
- No colored/gradient backgrounds or gradient blocks anywhere — only bklit's own
  in-chart default gradients (Area fill) and glows are allowed.
- `data.json` contract keys unchanged: `window {start,end}`,
  `tokens [{date,input,output,reasoning}]`, `agents [{agent,tokens}]`,
  `skills [{name,count}]`, `mcp [{name,count}]`, `heatmap [{date,tokens}]`.
- Every new Python module (none expected here) starts with
  `from __future__ import annotations`.
- Branch: `feature/dashboard-compact-redesign`.
