# Dashboard multilingual support (Korean/English) — design

Date: 2026-07-23
Status: Approved (design), pending implementation plan

## Goal

Let the interactive localhost dashboard (`agent-usage dashboard`) render its UI
in Korean or English, chosen via a CLI flag. Covers: static section titles,
chart legends/labels, loading/error/empty states, number formatting (K/M/B/T
vs 만/억/조), and date formatting.

## Non-goals (YAGNI)

- No in-app language switcher / toggle UI. Language is fixed for the life of
  the served session, set at launch time only.
- No i18n library (react-i18next, etc.) — small fixed string set, a plain
  dictionary + lookup function is sufficient.
- No translation of user data: skill names, MCP server names, and agent names
  are rendered exactly as they appear in `data.json`, in both languages.
- No change to `data.json` shape or the Python-side payload builder's field
  values (aside from the one exception below) — this is a UI-only feature.

## CLI flag → UI flow

- Add `--lang {en,ko}` (default `en`) to the `dashboard` CLI command
  (`src/agent_usage/cli.py`), validated against the fixed choice set.
- Thread it through `commands/dashboard.py::run(...)` as a `lang: str` param
  into `dashboard/server.py::serve(...)`.
- `serve()` sets `<html lang="...">` and injects a small inline script (e.g.
  `window.__LANG__ = "ko";`) into the served `index.html` before the app
  bundle loads. No query param, no change to `data.json`.
- React reads `window.__LANG__` once at startup (default `"en"` if absent).

## Translation layer (dashboard-ui)

New `dashboard-ui/src/i18n.ts`:

- `type Lang = "en" | "ko"`
- `getLang(): Lang` — reads `window.__LANG__`, falls back to `"en"`.
- `translations: Record<Lang, Record<string, string>>` — flat key → string map.
- `t(key: string): string` — looks up `translations[getLang()][key]`.

### Strings covered

| Key | English | Korean | Source |
|---|---|---|---|
| `title.tokenUsage` | Total Token Usage | 총 토큰 사용량 | App.tsx |
| `title.usageByAgent` | Usage by Agent | 에이전트별 사용량 | App.tsx |
| `title.skillUsage` | Skill Usage | 스킬 사용량 | App.tsx |
| `title.mcpUsage` | MCP Usage | MCP 사용량 | App.tsx |
| `title.activity` | Activity | 활동 | App.tsx |
| `legend.input` | Input | 입력 | TokenArea.tsx |
| `legend.output` | Output | 출력 | TokenArea.tsx |
| `legend.reasoning` | Reasoning | 추론 | TokenArea.tsx |
| `center.totalTokens` | Total tokens | 총 토큰 | AgentRing.tsx |
| `center.total` | Total | 총계 | UsageDonut.tsx |
| `heatmap.less` | Less | 적음 | CalendarHeatmap.tsx |
| `heatmap.more` | More | 많음 | CalendarHeatmap.tsx |
| `state.loading` | Loading… | 불러오는 중… | App.tsx |
| `state.error` | Failed to load data: | 데이터를 불러오지 못했습니다: | App.tsx |
| `state.noData` | No data yet. | 아직 데이터가 없습니다. | UsageDonut.tsx |
| `state.noTokenActivity` | No token activity in this window. | 이 기간에 토큰 활동이 없습니다. | TokenArea.tsx |
| `state.noAgentActivity` | No agent activity yet. | 아직 에이전트 활동이 없습니다. | AgentRing.tsx |
| `state.noActivity` | No activity recorded yet. | 아직 기록된 활동이 없습니다. | CalendarHeatmap.tsx |
| `heatmap.tokens` | Tokens | 토큰 | CalendarHeatmap.tsx (single-day tooltip fallback label) |
| `bucket.other` | Other | 기타 | server-generated bucket label (see exception below) |

The per-day calendar tooltip title (`hover.datum.date`, a raw `YYYY-MM-DD`
string) is left unformatted in both languages — it's an unambiguous ISO date,
not natural-language text, so localizing it adds no clarity.

### Untranslated (kept as raw data)

- `data.skills[].name`, `data.mcp[].name` — rendered verbatim via
  `LegendLabel` / tooltip, in both languages.
- `data.agents[].agent` — same.

### Exception: the "Other" bucket

`bucket_top_n` (`render/_counters.py`) synthesizes an `OTHER_LABEL = "Other"`
entry when skills/MCP servers exceed `--pie-top-n`. This is a UI-generated
label, not a real skill/MCP name from source data, so it is translated like
any other static string rather than passed through verbatim. The frontend
matches on the literal string `"Other"` from the payload to swap in `t("bucket.other")`.

## Numbers & dates

Both already use `Intl` APIs with a hardcoded `"en-US"` locale — swapping the
locale argument for the active language is sufficient, no manual suffix
tables needed:

- `chart-formatters.ts`: `intFmt`, `shortDateFmt`, `weekdayDateFmt`,
  `hmsTimeFmt` — change `"en-US"` to `getLang() === "ko" ? "ko-KR" : "en-US"`.
- `chart-stat-flow.tsx`: `new Intl.NumberFormat(undefined, formatOptions)` —
  change `undefined` to the resolved locale string. `notation: "compact"`
  already produces 만/억/조 for `ko-KR` and K/M/B/T for `en-US` natively.
- `AgentRing.tsx`'s `formatOptions={{ notation: "compact", ... }}` — no change
  needed, consumed by the now-locale-aware `chart-stat-flow.tsx`.
- Window date range in `App.tsx` (`data.window.start → data.window.end`) —
  currently raw ISO strings; format them through the locale-aware date
  formatter instead of printing raw.

## Testing

- Unit test `i18n.ts`: `t()` returns correct string per lang, falls back to
  `"en"` when `window.__LANG__` is unset or invalid.
- Unit test number/date formatters produce Korean-style compact notation
  when `ko-KR` is active (spot-check e.g. `12_340_000` → contains `만`).
- CLI test: `--lang ko` rejects invalid values, defaults to `en` when omitted,
  and is threaded into the served HTML's `window.__LANG__`.
- Manual/proofshot check: launch dashboard with `--lang ko`, confirm titles,
  legends, and Skill/MCP names (unchanged) render correctly in the browser.
