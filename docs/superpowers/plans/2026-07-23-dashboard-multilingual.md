# Dashboard Multilingual Support (Korean/English) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `tomax dashboard` serve its React UI in Korean or English via a new `--lang {en,ko}` CLI flag, translating static titles/legends/states and switching number/date formatting, while leaving skill/MCP/agent names untouched.

**Architecture:** A `--lang` CLi flag flows through `commands/dashboard.py` into `dashboard/server.py`, which injects `window.__LANG__` into the served `index.html` before the app bundle loads. The React app reads it once at startup via a new `src/i18n.ts` module (`getLang()`, `getLocale()`, `t(key)`) with no runtime switcher, no i18n library, no `data.json` changes.

**Tech Stack:** Python (typer CLI, stdlib `http.server`), React/TypeScript (Vite), `Intl.NumberFormat`/`Intl.DateTimeFormat` for locale-aware numbers and dates.

## Global Constraints

- Full string/translation inventory, CLI flow, and the "Other" bucket exception are defined in `docs/superpowers/specs/2026-07-23-dashboard-multilingual-design.md` — treat that table as the source of truth for exact English/Korean copy.
- Skill names (`data.skills[].name`), MCP names (`data.mcp[].name`), and agent names (`data.agents[].agent`, via `agentLabel()`) are never translated — passed through verbatim in both languages.
- Exception: the server-generated `"Other"` bucket label (`OTHER_LABEL` in `src/tomax/render/_counters.py`) IS translated — it's a synthesized UI label, not real vendor data.
- No in-app language switcher. Language is fixed for the life of the served session, chosen at launch via `--lang` (default `en`).
- `dashboard-ui/` has no JS test runner configured (no vitest/jest, no `.test.*` files, `package.json` scripts are only `dev`/`build`/`preview`). Per YAGNI, this plan does not add one — frontend tasks are verified by `npm run build` (TypeScript compiles clean) plus a final manual/proofshot check, not automated unit tests. Python-side changes use the repo's existing `pytest` setup.
- The per-day calendar tooltip title (raw `YYYY-MM-DD` string) stays unformatted in both languages — it's unambiguous ISO, not natural-language text.

---

### Task 1: Thread `--lang` through the CLI and `dashboard` command

**Files:**
- Modify: `src/tomax/cli.py` (`dashboard` command, ~line 129-163)
- Modify: `src/tomax/commands/dashboard.py` (`run(...)`, whole file)
- Test: `tests/commands/test_cli.py`
- Test: `tests/commands/test_dashboard_cli.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `dashboard_command.run(..., lang: str)` — a `lang` keyword-only argument accepted by `run()` and forwarded to `serve(..., lang=lang)`. Later tasks (Task 2) rely on `serve()` accepting this `lang` keyword.

- [ ] **Step 1: Write the failing CLI validation test**

Add to `tests/commands/test_cli.py`, right after `test_render_rejects_a_pie_top_n_below_one`:

```python
def test_dashboard_rejects_an_invalid_lang(tmp_path, monkeypatch) -> None:
    _patch_local_paths(monkeypatch, tmp_path)
    _patch_missing_sources(monkeypatch, tmp_path)

    result = runner.invoke(app, ["dashboard", "--lang", "fr", "--no-open"])

    assert result.exit_code != 0
    assert "lang" in _strip_ansi(result.output).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/commands/test_cli.py::test_dashboard_rejects_an_invalid_lang -v`
Expected: FAIL (no `--lang` option registered — typer reports "No such option")

- [ ] **Step 3: Add `--lang` to the `dashboard` CLI command**

In `src/tomax/cli.py`, inside `def dashboard(...)` (~line 130), add the parameter after `pie_top_n`:

```python
    pie_top_n: int = typer.Option(
        6, "--pie-top-n", help="Max Skills/MCP pie slices before bucketing the rest into 'Other'."
    ),
    lang: str = typer.Option(
        "en", "--lang", help="Dashboard UI language: 'en' (default) or 'ko'."
    ),
) -> None:
    """Serve an interactive localhost usage dashboard (local data, or --all-devices)."""
    if pie_top_n < 1:
        raise typer.BadParameter("--pie-top-n must be at least 1")
    if lang not in ("en", "ko"):
        raise typer.BadParameter("--lang must be 'en' or 'ko'")
```

Then in the `dashboard_command.run(...)` call inside the same function (~line 149-160), add `lang=lang,` alongside the existing `pie_top_n=pie_top_n,` line.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/commands/test_cli.py::test_dashboard_rejects_an_invalid_lang -v`
Expected: PASS

- [ ] **Step 5: Update `commands/dashboard.py::run()` to accept and forward `lang`**

In `src/tomax/commands/dashboard.py`, add `lang: str,` to the `run(...)` signature (after `today: date,`, before `tmp_stage_dir: Path,` — keyword-only params, order among keyword-only args doesn't matter functionally, but keep it readable next to `pie_top_n`):

```python
def run(
    *,
    ledger_path: Path,
    config_path: Path,
    all_devices: bool,
    port: int,
    open_browser: bool,
    pie_top_n: int,
    lang: str,
    ui_dir: Path,
    force_build: bool,
    today: date,
    tmp_stage_dir: Path,
) -> None:
```

And update the final `serve(...)` call at the bottom of the function:

```python
    serve(data, dist_dir=dist_dir, port=port, open_browser=open_browser, lang=lang)
```

- [ ] **Step 6: Update the existing `test_dashboard_cli.py` unit tests for the new required argument**

In `tests/commands/test_dashboard_cli.py`, update `fake_serve` in `test_run_builds_payload_and_serves` to accept the new keyword:

```python
    def fake_serve(data, *, dist_dir, port, open_browser, lang):
        calls["data"] = data
        calls["dist_dir"] = dist_dir
        calls["port"] = port
        calls["open_browser"] = open_browser
        calls["lang"] = lang
```

Add `lang="ko",` to both `dashboard_command.run(...)` calls in that file (in `test_run_builds_payload_and_serves` and `test_run_reports_missing_repo_target`), and add this assertion at the end of `test_run_builds_payload_and_serves`:

```python
    assert calls["lang"] == "ko"
```

- [ ] **Step 7: Run the full test file to verify it passes**

Run: `pytest tests/commands/test_dashboard_cli.py tests/commands/test_cli.py -v`
Expected: PASS (all tests, including the two updated ones and the new one)

- [ ] **Step 8: Commit**

```bash
git add src/tomax/cli.py src/tomax/commands/dashboard.py tests/commands/test_cli.py tests/commands/test_dashboard_cli.py
git commit -m "feat(cli): add --lang flag to dashboard command"
```

---

### Task 2: Inject `window.__LANG__` into the served HTML

**Files:**
- Modify: `src/tomax/dashboard/server.py` (whole file)
- Test: `tests/dashboard/test_server.py`

**Interfaces:**
- Consumes: `lang: str` from Task 1's `commands/dashboard.py::run()` call into `serve(...)`.
- Produces: `make_server(data, *, dist_dir, host="127.0.0.1", port=8000, lang="en")` and `serve(data, *, dist_dir, host="127.0.0.1", port=8000, open_browser=True, lang="en")` — both gain a `lang` keyword (defaulting to `"en"` so existing call sites without it keep working). The served `/` and `/index.html` responses contain an injected `<script>window.__LANG__="...";</script>` and (best-effort) an updated `<html lang="...">` attribute. This is what the frontend's `i18n.ts` (Task 3) reads via `window.__LANG__`.

- [ ] **Step 1: Write the failing test for lang injection**

Add to `tests/dashboard/test_server.py`, after `test_server_serves_index_and_injects_data_json`:

```python
def test_server_injects_lang_into_html(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        '<!doctype html><html lang="en"><head></head><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )

    server = make_server({}, dist_dir=dist, port=0, lang="ko")
    host, port = server.server_address
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, body, _ = _get(f"{base}/")
        assert status == 200
        assert b'window.__LANG__="ko";' in body
        assert b'lang="ko"' in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dashboard/test_server.py::test_server_injects_lang_into_html -v`
Expected: FAIL (`make_server()` raises `TypeError: unexpected keyword argument 'lang'`)

- [ ] **Step 3: Implement HTML injection in `server.py`**

Replace the full contents of `src/tomax/dashboard/server.py` with:

```python
"""Serve the interactive dashboard on localhost: committed dist/ plus injected data.json."""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _inject_lang(html: str, lang: str) -> str:
    """Set <html lang="..."> (best-effort) and inject a window.__LANG__ script.

    The script runs before the deferred module bundle, so the React app can
    read window.__LANG__ synchronously at startup.
    """
    if 'lang="en"' in html:
        html = html.replace('lang="en"', f'lang="{lang}"', 1)
    script = f"<script>window.__LANG__={json.dumps(lang)};</script>"
    tag_start = html.find("<html")
    if tag_start == -1:
        return script + html
    tag_end = html.find(">", tag_start)
    if tag_end == -1:
        return script + html
    return html[: tag_end + 1] + script + html[tag_end + 1 :]


class _DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, data_bytes: bytes, html_bytes: bytes, dist_dir: Path, **kwargs) -> None:
        self._data_bytes = data_bytes
        self._html_bytes = html_bytes
        super().__init__(*args, directory=str(dist_dir), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0]
        if path == "/data.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(self._data_bytes)))
            self.end_headers()
            self.wfile.write(self._data_bytes)
            return
        # Serve the lang-injected index.html for "/", "/index.html", and any
        # unknown client-side route (SPA fallback).
        translated = Path(self.translate_path(self.path))
        if path in ("/", "/index.html") or (not translated.exists() and "." not in Path(path).name):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(self._html_bytes)))
            self.end_headers()
            self.wfile.write(self._html_bytes)
            return
        super().do_GET()

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


def make_server(
    data: dict,
    *,
    dist_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    lang: str = "en",
) -> ThreadingHTTPServer:
    """Build (but do not start) the localhost dashboard server."""
    html_text = (dist_dir / "index.html").read_text(encoding="utf-8")
    handler = partial(
        _DashboardHandler,
        data_bytes=json.dumps(data).encode("utf-8"),
        html_bytes=_inject_lang(html_text, lang).encode("utf-8"),
        dist_dir=dist_dir,
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    data: dict,
    *,
    dist_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
    lang: str = "en",
) -> None:
    """Serve the dashboard until interrupted (Ctrl-C)."""
    server = make_server(data, dist_dir=dist_dir, host=host, port=port, lang=lang)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"
    print(f"tomax: dashboard serving at {url} (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dashboard/test_server.py -v`
Expected: PASS (all tests in the file, including the two pre-existing ones — the SPA-fallback and English-default paths are unaffected since `lang` defaults to `"en"` and the pre-existing minimal-HTML test has no `<html>` tag, so injection prepends the script and leaves `"dash"` intact)

- [ ] **Step 5: Commit**

```bash
git add src/tomax/dashboard/server.py tests/dashboard/test_server.py
git commit -m "feat(dashboard): inject window.__LANG__ into served index.html"
```

---

### Task 3: Frontend `i18n.ts` foundation module

**Files:**
- Create: `dashboard-ui/src/i18n.ts`

**Interfaces:**
- Consumes: `window.__LANG__` (a `string | undefined`, set by Task 2's server injection before the module script runs).
- Produces: `type Lang = "en" | "ko"`, `getLang(): Lang`, `getLocale(): string` (`"ko-KR"` or `"en-US"`), `t(key: string): string`. All later tasks (4-9) import `t`, `getLang`, and/or `getLocale` from `"@/i18n"`.

- [ ] **Step 1: Write `i18n.ts`**

```typescript
export type Lang = "en" | "ko";

declare global {
  interface Window {
    __LANG__?: string;
  }
}

export function getLang(): Lang {
  return typeof window !== "undefined" && window.__LANG__ === "ko" ? "ko" : "en";
}

export function getLocale(): string {
  return getLang() === "ko" ? "ko-KR" : "en-US";
}

const translations: Record<Lang, Record<string, string>> = {
  en: {
    "title.tokenUsage": "Total Token Usage",
    "title.usageByAgent": "Usage by Agent",
    "title.skillUsage": "Skill Usage",
    "title.mcpUsage": "MCP Usage",
    "title.activity": "Activity",
    "legend.input": "Input",
    "legend.output": "Output",
    "legend.reasoning": "Reasoning",
    "center.totalTokens": "Total tokens",
    "center.total": "Total",
    "heatmap.less": "Less",
    "heatmap.more": "More",
    "heatmap.tokens": "Tokens",
    "state.loading": "Loading…",
    "state.error": "Failed to load data:",
    "state.noData": "No data yet.",
    "state.noTokenActivity": "No token activity in this window.",
    "state.noAgentActivity": "No agent activity yet.",
    "state.noActivity": "No activity recorded yet.",
    "bucket.other": "Other",
  },
  ko: {
    "title.tokenUsage": "총 토큰 사용량",
    "title.usageByAgent": "에이전트별 사용량",
    "title.skillUsage": "스킬 사용량",
    "title.mcpUsage": "MCP 사용량",
    "title.activity": "활동",
    "legend.input": "입력",
    "legend.output": "출력",
    "legend.reasoning": "추론",
    "center.totalTokens": "총 토큰",
    "center.total": "총계",
    "heatmap.less": "적음",
    "heatmap.more": "많음",
    "heatmap.tokens": "토큰",
    "state.loading": "불러오는 중…",
    "state.error": "데이터를 불러오지 못했습니다:",
    "state.noData": "아직 데이터가 없습니다.",
    "state.noTokenActivity": "이 기간에 토큰 활동이 없습니다.",
    "state.noAgentActivity": "아직 에이전트 활동이 없습니다.",
    "state.noActivity": "아직 기록된 활동이 없습니다.",
    "bucket.other": "기타",
  },
};

export function t(key: string): string {
  return translations[getLang()][key] ?? key;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard-ui && npm run build`
Expected: build succeeds (no other file imports `i18n.ts` yet, so this only proves the new file itself is valid TypeScript — unused-export warnings, if any, are not build errors under this project's `tsconfig`)

- [ ] **Step 3: Commit**

```bash
git add dashboard-ui/src/i18n.ts
git commit -m "feat(dashboard-ui): add i18n translation lookup module"
```

---

### Task 4: Locale-aware number and date formatting

**Files:**
- Modify: `dashboard-ui/src/components/charts/chart-formatters.ts` (whole file)
- Modify: `dashboard-ui/src/components/charts/chart-stat-flow.tsx` (lines 1-38, 96-116)

**Interfaces:**
- Consumes: `getLocale()` from Task 3's `"@/i18n"`.
- Produces: `chart-formatters.ts` now exports an additional `windowDateFmt` (year/month/day) and a `parseISODate(iso: string): Date` helper — Task 5 (App.tsx) uses both for the window date range. All exports (`shortDateFmt`, `weekdayDateFmt`, `hmsTimeFmt`, `intFmt`, `windowDateFmt`) are now locale-aware instead of hardcoded `"en-US"`. `chart-stat-flow.tsx`'s `ChartStatFlow` component now formats numbers (both the static fallback and the animated `NumberFlow`) using the active locale.

- [ ] **Step 1: Update `chart-formatters.ts`**

Replace the full contents of `dashboard-ui/src/components/charts/chart-formatters.ts` with:

```typescript
import { getLocale } from "@/i18n";

const locale = getLocale();

export const shortDateFmt = new Intl.DateTimeFormat(locale, {
  month: "short",
  day: "numeric",
});

export const weekdayDateFmt = new Intl.DateTimeFormat(locale, {
  weekday: "short",
  month: "short",
  day: "numeric",
});

export const hmsTimeFmt = new Intl.DateTimeFormat(locale, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export const windowDateFmt = new Intl.DateTimeFormat(locale, {
  year: "numeric",
  month: "short",
  day: "numeric",
});

// `Intl.NumberFormat.prototype.format` is a bound getter — safe to extract.
export const intFmt = new Intl.NumberFormat(locale).format;

/** Parse a `YYYY-MM-DD` string as a local date (avoids UTC-midnight day-shift bugs). */
export function parseISODate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
```

- [ ] **Step 2: Update `chart-stat-flow.tsx` to use the active locale**

In `dashboard-ui/src/components/charts/chart-stat-flow.tsx`, add the import at the top (after the existing `cn` import, line 5):

```typescript
import { getLocale } from "@/i18n";
```

Replace `formatStatValue` (lines 28-38):

```typescript
function formatStatValue(
  value: number,
  formatOptions: ChartStatFlowFormat,
  prefix?: string,
  suffix?: string
): string {
  const formatted = new Intl.NumberFormat(getLocale(), formatOptions).format(
    value
  );
  return `${prefix ?? ""}${formatted}${suffix ?? ""}`;
}
```

In the `ChartStatFlow` component's returned JSX (~line 104-112), add `locales={getLocale()}` to the `<NumberFlow>` element:

```typescript
          <NumberFlow
            format={formatOptions}
            locales={getLocale()}
            isolate
            prefix={prefix}
            suffix={suffix}
            value={value}
            willChange
          />
```

- [ ] **Step 3: Verify it compiles**

Run: `cd dashboard-ui && npm run build`
Expected: build succeeds

- [ ] **Step 4: Commit**

```bash
git add dashboard-ui/src/components/charts/chart-formatters.ts dashboard-ui/src/components/charts/chart-stat-flow.tsx
git commit -m "feat(dashboard-ui): make number and date formatting locale-aware"
```

---

### Task 5: Translate `App.tsx` titles, loading/error states, and window date range

**Files:**
- Modify: `dashboard-ui/src/App.tsx` (whole file)

**Interfaces:**
- Consumes: `t` from `"@/i18n"` (Task 3), `parseISODate`/`windowDateFmt` from `"@/components/charts/chart-formatters"` (Task 4).
- Produces: nothing consumed by later tasks — this is a leaf.

- [ ] **Step 1: Update `App.tsx`**

Replace the full contents of `dashboard-ui/src/App.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { AgentRing } from "./charts/AgentRing";
import { CalendarHeatmap } from "./charts/CalendarHeatmap";
import { TokenArea } from "./charts/TokenArea";
import { UsageDonut } from "./charts/UsageDonut";
import { parseISODate, windowDateFmt } from "@/components/charts/chart-formatters";
import { t } from "./i18n";

type Data = {
  window: { start: string; end: string };
  tokens: { date: string; input: number; output: number; reasoning: number }[];
  agents: { agent: string; tokens: number }[];
  skills: { name: string; count: number }[];
  mcp: { name: string; count: number }[];
  heatmap: { date: string; tokens: number }[];
};

export default function App() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("data.json")
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="dashboard empty">{t("state.error")} {error}</div>;
  if (!data) return <div className="dashboard empty">{t("state.loading")}</div>;

  return (
    <div className="dashboard">
      <section className="block">
        <h2>
          {t("title.tokenUsage")}{" "}
          <span className="window">
            {windowDateFmt.format(parseISODate(data.window.start))} →{" "}
            {windowDateFmt.format(parseISODate(data.window.end))}
          </span>
        </h2>
        <TokenArea data={data.tokens} />
      </section>
      <section className="block">
        <h2>{t("title.usageByAgent")}</h2>
        <AgentRing data={data.agents} />
      </section>
      <div className="row-two">
        <section className="block">
          <h2>{t("title.skillUsage")}</h2>
          <UsageDonut data={data.skills} />
        </section>
        <section className="block">
          <h2>{t("title.mcpUsage")}</h2>
          <UsageDonut data={data.mcp} />
        </section>
      </div>
      <section className="block">
        <h2>{t("title.activity")}</h2>
        <CalendarHeatmap data={data.heatmap} />
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard-ui/src/App.tsx
git commit -m "feat(dashboard-ui): translate section titles and localize window date range"
```

---

### Task 6: Translate `TokenArea.tsx` legend labels and empty state

**Files:**
- Modify: `dashboard-ui/src/charts/TokenArea.tsx` (whole file)

**Interfaces:**
- Consumes: `t` from `"@/i18n"` (Task 3).
- Produces: nothing consumed by later tasks — leaf.

- [ ] **Step 1: Update `TokenArea.tsx`**

Replace the full contents of `dashboard-ui/src/charts/TokenArea.tsx` with:

```tsx
import { AreaChart, Area } from "@/components/charts/area-chart";
import { Grid } from "@/components/charts/grid";
import { XAxis } from "@/components/charts/x-axis";
import { YAxis } from "@/components/charts/y-axis";
import { ChartTooltip } from "@/components/charts/tooltip";
import { SERIES_COLORS } from "./names";
import { t } from "@/i18n";

export type TokenPoint = {
  date: string;
  input: number;
  output: number;
  reasoning: number;
};

export function TokenArea({ data }: { data: TokenPoint[] }) {
  if (data.length === 0) return <div className="empty">{t("state.noTokenActivity")}</div>;

  return (
    <>
      <AreaChart data={data} xDataKey="date" aspectRatio="3 / 1" margin={{ left: 50 }}>
        <Grid horizontal />
        <Area dataKey="input" fill={SERIES_COLORS.input} />
        <Area dataKey="output" fill={SERIES_COLORS.output} />
        <Area dataKey="reasoning" fill={SERIES_COLORS.reasoning} />
        <YAxis formatLargeNumbers />
        <XAxis />
        <ChartTooltip
          showDatePill
          rows={(p) => [
            { label: t("legend.input"), value: p.input as number, color: SERIES_COLORS.input },
            { label: t("legend.output"), value: p.output as number, color: SERIES_COLORS.output },
            {
              label: t("legend.reasoning"),
              value: p.reasoning as number,
              color: SERIES_COLORS.reasoning,
            },
          ]}
        />
      </AreaChart>
      <div className="legend">
        {(["input", "output", "reasoning"] as const).map((k) => (
          <span className="item" key={k}>
            <span className="swatch" style={{ background: SERIES_COLORS[k] }} />
            {t(`legend.${k}`)}
          </span>
        ))}
      </div>
    </>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard-ui/src/charts/TokenArea.tsx
git commit -m "feat(dashboard-ui): translate token area legend and empty state"
```

---

### Task 7: Translate `AgentRing.tsx` center label and empty state

**Files:**
- Modify: `dashboard-ui/src/charts/AgentRing.tsx` (whole file)

**Interfaces:**
- Consumes: `t` from `"@/i18n"` (Task 3).
- Produces: nothing consumed by later tasks — leaf. (Agent names via `agentLabel()` are untouched — brand names, not translated.)

- [ ] **Step 1: Update `AgentRing.tsx`**

Replace the full contents of `dashboard-ui/src/charts/AgentRing.tsx` with:

```tsx
import { useState } from "react";
import { RingChart } from "@/components/charts/ring-chart";
import { Ring } from "@/components/charts/ring";
import { RingCenter } from "@/components/charts/ring-center";
import {
  Legend,
  LegendItem,
  LegendLabel,
  LegendMarker,
  LegendProgress,
  LegendValue,
} from "@/components/charts/legend";
import { agentColor, agentLabel, CATEGORY_COLORS } from "./names";
import { t } from "@/i18n";

export type AgentDatum = { agent: string; tokens: number };

export function AgentRing({ data }: { data: AgentDatum[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const active = data.filter((d) => d.tokens > 0);
  const total = active.reduce((sum, d) => sum + d.tokens, 0);
  if (total <= 0) return <div className="empty">{t("state.noAgentActivity")}</div>;

  const items = active.map((d, i) => ({
    label: agentLabel(d.agent),
    value: d.tokens,
    maxValue: total,
    color: agentColor(d.agent, CATEGORY_COLORS[i % CATEGORY_COLORS.length]),
  }));

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        gap: 32,
        alignItems: "center",
        justifyContent: "center",
        flexWrap: "wrap",
      }}
    >
      <RingChart
        data={items}
        size={280}
        strokeWidth={20}
        hoveredIndex={hoveredIndex}
        onHoverChange={setHoveredIndex}
      >
        {items.map((_, i) => (
          <Ring key={i} index={i} />
        ))}
        <RingCenter
          defaultLabel={t("center.totalTokens")}
          formatOptions={{ notation: "compact", maximumFractionDigits: 1 }}
        />
      </RingChart>
      <Legend items={items} hoveredIndex={hoveredIndex} onHoverChange={setHoveredIndex}>
        <LegendItem>
          <LegendMarker />
          <LegendLabel />
          <LegendValue showPercentage />
          <LegendProgress />
        </LegendItem>
      </Legend>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard-ui/src/charts/AgentRing.tsx
git commit -m "feat(dashboard-ui): translate agent ring center label and empty state"
```

---

### Task 8: Translate `UsageDonut.tsx` center label, empty state, and the "Other" bucket

**Files:**
- Modify: `dashboard-ui/src/charts/UsageDonut.tsx` (whole file)

**Interfaces:**
- Consumes: `t` from `"@/i18n"` (Task 3).
- Produces: nothing consumed by later tasks — leaf. Real skill/MCP `name` values are passed through unchanged; only the literal `"Other"` bucket label (matching `OTHER_LABEL` in `src/tomax/render/_counters.py`) is swapped for its translation.

- [ ] **Step 1: Update `UsageDonut.tsx`**

Replace the full contents of `dashboard-ui/src/charts/UsageDonut.tsx` with:

```tsx
import { useState } from "react";
import { PieChart } from "@/components/charts/pie-chart";
import { PieSlice } from "@/components/charts/pie-slice";
import { PieCenter } from "@/components/charts/pie-center";
import { TooltipContent } from "@/components/charts/tooltip/tooltip-content";
import {
  Legend,
  LegendItem,
  LegendLabel,
  LegendMarker,
  LegendValue,
} from "@/components/charts/legend";
import { CATEGORY_COLORS } from "./names";
import { t } from "@/i18n";

export type UsageDatum = { name: string; count: number };

// Matches OTHER_LABEL in src/tomax/render/_counters.py — a
// server-synthesized bucket, not a real skill/MCP name, so it's translated.
const OTHER_LABEL = "Other";

export function UsageDonut({ data }: { data: UsageDatum[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  const active = data.filter((d) => d.count > 0);
  const total = active.reduce((sum, d) => sum + d.count, 0);
  if (total <= 0) return <div className="empty">{t("state.noData")}</div>;

  const slices = active.map((d, i) => ({
    label: d.name === OTHER_LABEL ? t("bucket.other") : d.name,
    value: d.count,
    maxValue: total,
    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
  }));

  const hovered = hoveredIndex !== null ? slices[hoveredIndex] : null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        gap: 32,
        alignItems: "center",
        justifyContent: "center",
        flexWrap: "wrap",
      }}
    >
      <div
        style={{ position: "relative" }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          setHoverPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
        }}
      >
        <PieChart
          data={slices}
          size={220}
          innerRadius={64}
          padAngle={0.02}
          hoveredIndex={hoveredIndex}
          onHoverChange={setHoveredIndex}
        >
          {slices.map((_, i) => (
            <PieSlice key={i} index={i} />
          ))}
          <PieCenter defaultLabel={t("center.total")} />
        </PieChart>
        {hovered && hoverPos && (
          <div
            className="pointer-events-none absolute z-50"
            style={{
              left: hoverPos.x,
              top: hoverPos.y,
              transform: "translate(-50%, -100%)",
              marginTop: -12,
            }}
          >
            <div className="min-w-[140px] overflow-hidden rounded-lg bg-chart-tooltip-background shadow-lg">
              <TooltipContent
                rows={[
                  {
                    label: hovered.label,
                    color: hovered.color,
                    value: `${hovered.value} (${Math.round((hovered.value / total) * 100)}%)`,
                  },
                ]}
              />
            </div>
          </div>
        )}
      </div>
      <Legend
        items={slices}
        hoveredIndex={hoveredIndex}
        onHoverChange={setHoveredIndex}
        className="grid grid-cols-2 gap-x-4 gap-y-1"
      >
        <LegendItem className="flex items-center gap-2">
          <LegendMarker />
          <LegendLabel className="flex-1 truncate" />
          <LegendValue showPercentage />
        </LegendItem>
      </Legend>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard-ui/src/charts/UsageDonut.tsx
git commit -m "feat(dashboard-ui): translate usage donut center label, empty state, and Other bucket"
```

---

### Task 9: Translate `CalendarHeatmap.tsx` scale labels, tooltip fallback, and empty state

**Files:**
- Modify: `dashboard-ui/src/charts/CalendarHeatmap.tsx` (whole file)

**Interfaces:**
- Consumes: `t` from `"@/i18n"` (Task 3).
- Produces: nothing consumed by later tasks — leaf. The per-day tooltip title (`hover.datum.date`) stays a raw ISO string, unformatted, per the spec.

- [ ] **Step 1: Update `CalendarHeatmap.tsx`**

Replace the full contents of `dashboard-ui/src/charts/CalendarHeatmap.tsx` with:

```tsx
import { useState } from "react";
import { TooltipContent } from "@/components/charts/tooltip/tooltip-content";
import { agentLabel, CATEGORY_COLORS } from "./names";
import { t } from "@/i18n";

export type HeatDatum = {
  date: string;
  tokens: number;
  byAgent?: { agent: string; tokens: number }[];
};

// Grayscale Less -> More (flat fills, no gradient).
const SCALE = ["#161B22", "#2D333B", "#4A5568", "#8B949E", "#E5E7EB"];

function parseDay(d: string): Date {
  const [y, m, day] = d.split("-").map(Number);
  return new Date(y, m - 1, day);
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function CalendarHeatmap({ data }: { data: HeatDatum[] }) {
  const [hover, setHover] = useState<{ x: number; y: number; datum: HeatDatum } | null>(null);

  if (data.length === 0) return <div className="empty">{t("state.noActivity")}</div>;

  const byDatum = new Map(data.map((d) => [d.date, d]));
  const byDate = new Map(data.map((d) => [d.date, d.tokens]));
  const maxTokens = Math.max(...data.map((d) => d.tokens), 1);

  const first = parseDay(data[0].date);
  const last = parseDay(data[data.length - 1].date);

  // Start on the Sunday on/before the first date.
  const start = new Date(first);
  start.setDate(start.getDate() - start.getDay());

  const weeks: Date[][] = [];
  let cursor = new Date(start);
  while (cursor <= last) {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) {
      week.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }

  const bucket = (tokens: number): string => {
    if (tokens <= 0) return SCALE[0];
    const idx = 1 + Math.floor((tokens / maxTokens) * (SCALE.length - 2));
    return SCALE[Math.min(idx, SCALE.length - 1)];
  };

  return (
    <div className="cal-wrap">
      <div className="cal">
        {weeks.map((week, wi) => (
          <div className="col" key={wi}>
            {week.map((day) => {
              const key = iso(day);
              const tokens = byDate.get(key);
              const inRange = day >= first && day <= last;
              const color = inRange && tokens !== undefined ? bucket(tokens) : "transparent";
              const datum = byDatum.get(key);
              return (
                <div
                  className="cell"
                  key={key}
                  style={{ background: color }}
                  onMouseEnter={(e) => {
                    if (!inRange || !datum) return;
                    const rect = e.currentTarget.getBoundingClientRect();
                    const parentRect = e.currentTarget.closest(".cal-wrap")!.getBoundingClientRect();
                    setHover({
                      x: rect.left - parentRect.left + rect.width / 2,
                      y: rect.top - parentRect.top,
                      datum,
                    });
                  }}
                  onMouseLeave={() => setHover(null)}
                />
              );
            })}
          </div>
        ))}
      </div>
      {hover && (
        <div
          className="cal-tooltip"
          style={{ left: hover.x, top: hover.y }}
        >
          <TooltipContent
            title={hover.datum.date}
            rows={
              hover.datum.byAgent && hover.datum.byAgent.length > 0
                ? hover.datum.byAgent.map((a, i) => ({
                    label: agentLabel(a.agent),
                    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                    value: `${Math.round((a.tokens / hover.datum.tokens) * 100)}%`,
                  }))
                : [{ label: t("heatmap.tokens"), color: SCALE[SCALE.length - 1], value: hover.datum.tokens }]
            }
          />
        </div>
      )}
      <div className="cal-scale">
        <span>{t("heatmap.less")}</span>
        {SCALE.map((c) => (
          <span className="cell" key={c} style={{ background: c }} />
        ))}
        <span>{t("heatmap.more")}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard-ui && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard-ui/src/charts/CalendarHeatmap.tsx
git commit -m "feat(dashboard-ui): translate calendar heatmap scale labels and empty state"
```

---

### Task 10: End-to-end manual verification

**Files:** none (verification only)

**Interfaces:**
- Consumes: everything from Tasks 1-9.
- Produces: nothing — terminal task.

- [ ] **Step 1: Run the full Python test suite**

Run: `pytest tests/ -v`
Expected: PASS (all tests, including the Task 1/2 additions)

- [ ] **Step 2: Force a fresh UI build and launch in English**

Run: `tomax dashboard --rebuild --no-open --port 8931`

Open `http://127.0.0.1:8931` in a browser. Confirm:
- Titles read "Total Token Usage", "Usage by Agent", "Skill Usage", "MCP Usage", "Activity"
- Token area legend reads "Input"/"Output"/"Reasoning"
- Numbers use K/M/B/T compact notation
- Skill/MCP/agent names render as raw data (unchanged)

Stop the server with Ctrl-C.

- [ ] **Step 3: Launch in Korean and verify**

Run: `tomax dashboard --no-open --port 8931 --lang ko`

Open `http://127.0.0.1:8931`. Confirm:
- Page `<html>` tag has `lang="ko"` (view page source)
- Titles read "총 토큰 사용량", "에이전트별 사용량", "스킬 사용량", "MCP 사용량", "활동"
- Token legend reads "입력"/"출력"/"추론"
- Numbers use 만/억/조 compact notation (verify with a large-token test dataset if the local ledger doesn't naturally cross 10,000)
- Window date range and any "Other" bucket render in Korean
- Skill/MCP/agent names render as raw data, identical to the English run — NOT translated

Stop the server with Ctrl-C.

- [ ] **Step 4: Use the `run` skill or `proofshot` skill for a screenshotted record (optional but recommended)**

If available, invoke the `proofshot` skill to capture before/after screenshots of both language modes for the PR description.

- [ ] **Step 5: Final commit (if any fixups were needed during verification)**

```bash
git add -A
git commit -m "fix(dashboard): address issues found during multilingual manual verification"
```

(Skip this step entirely if no fixups were needed.)
