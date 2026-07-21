# Dashboard Compact Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Skills/MCP horizontal bar charts with height-capped pie charts, add a new agent usage-share bar, and trim the managed README dashboard's markdown scaffolding so the whole section renders shorter.

**Architecture:** All chart rendering stays in `src/agent_usage/render/plotly.py` as pure functions taking plain `Mapping`/`Sequence` data and returning PNG bytes (no model imports, matching the existing pattern). `render_dashboard` in `src/agent_usage/render/markdown.py` remains the single orchestration point tying aggregation, chart rendering, and markdown assembly together. A new `pie_top_n` parameter and a new `agent_share_chart_path` parameter flow from the two CLI entry points (`agent-usage render` and `scripts/build_profile_dashboard.py`) down through `commands/render.py` / `build_profile_dashboard.py` to `render_dashboard`.

**Tech Stack:** Python 3.11, Plotly `go.Figure`/`go.Pie`/`go.Bar`, Kaleido (static PNG export), pytest, Typer.

## Global Constraints

- Charts are pure functions of their inputs (deterministic PNG bytes for identical inputs) — required by the existing `test_plotly_png_rendering_is_deterministic` test and the spec's "Non-goals" (no client-side JS).
- Skills and MCP pies share a single `top_n` value; default is **6**.
- Agent-share bar uses **lifetime** `headline_total` tokens (not rolling 14-day).
- Agent-share segment order is always Hermes → Claude Code → Codex, never sorted by size.
- No raw HTML in the generated markdown — side-by-side Skills/MCP uses a plain markdown table.
- Every dropped heading in the new markdown layout must not remove any information — the PNG chart title already carries that text.

---

### Task 1: Pure helpers — `bucket_top_n` and `stacked_percentages`

**Files:**
- Modify: `src/agent_usage/render/plotly.py`
- Test: `tests/render/test_plotly.py`

**Interfaces:**
- Consumes: nothing new — `rank_usage(counters: Mapping[str, int]) -> list[tuple[str, int]]` already exists in this file.
- Produces:
  - `bucket_top_n(ranked: Sequence[tuple[str, int]], top_n: int) -> list[tuple[str, int]]`
  - `stacked_percentages(totals: Sequence[int]) -> list[int]`
  These are consumed by Task 2 and Task 3 respectively.

- [ ] **Step 1: Write the failing tests**

Add to `tests/render/test_plotly.py` (append after the existing `test_rank_usage_orders_most_used_first_then_name` test, before the bar chart test — the bar chart test and its import are still untouched in this task):

```python
from agent_usage.render.plotly import bucket_top_n, stacked_percentages


def test_bucket_top_n_keeps_all_entries_when_under_the_cap() -> None:
    ranked = [("alpha", 5), ("beta", 3)]

    assert bucket_top_n(ranked, top_n=5) == [("alpha", 5), ("beta", 3)]


def test_bucket_top_n_keeps_all_entries_when_exactly_at_the_cap() -> None:
    ranked = [("alpha", 5), ("beta", 3)]

    assert bucket_top_n(ranked, top_n=2) == [("alpha", 5), ("beta", 3)]


def test_bucket_top_n_sums_overflow_into_an_other_entry() -> None:
    ranked = [("alpha", 10), ("beta", 5), ("gamma", 3), ("delta", 1)]

    result = bucket_top_n(ranked, top_n=2)

    assert result == [("alpha", 10), ("beta", 5), ("Other", 4)]


def test_stacked_percentages_sum_to_exactly_100() -> None:
    assert sum(stacked_percentages([1, 1, 1])) == 100
    assert sum(stacked_percentages([7, 2, 1])) == 100
    assert sum(stacked_percentages([1, 0, 0])) == 100


def test_stacked_percentages_all_zero_returns_all_zero() -> None:
    assert stacked_percentages([0, 0, 0]) == [0, 0, 0]


def test_stacked_percentages_preserves_input_order() -> None:
    assert stacked_percentages([300, 100, 0]) == [75, 25, 0]
```

Move the new `from agent_usage.render.plotly import bucket_top_n, stacked_percentages` line up into the single existing import block at the top of the file instead of leaving it inline — the file currently has one `from agent_usage.render.plotly import (...)` block; add `bucket_top_n` and `stacked_percentages` to it alphabetically:

```python
from agent_usage.render.plotly import (
    bucket_top_n,
    rank_usage,
    render_stacked_token_chart,
    render_usage_bar_chart,
    stacked_percentages,
)
```

(Remove the separate inline import line shown above once it's merged into this block.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/render/test_plotly.py -v`
Expected: `ImportError: cannot import name 'bucket_top_n'` (and `stacked_percentages`) — the functions don't exist yet.

- [ ] **Step 3: Implement the two pure helpers**

In `src/agent_usage/render/plotly.py`, add directly after the existing `rank_usage` function (after line 37):

```python
_OTHER_LABEL = "Other"


def bucket_top_n(ranked: Sequence[tuple[str, int]], top_n: int) -> list[tuple[str, int]]:
    """Keep the top ``top_n`` ranked entries, summing the rest into one 'Other' entry."""
    kept = list(ranked[:top_n])
    overflow = ranked[top_n:]
    if overflow:
        kept.append((_OTHER_LABEL, sum(count for _, count in overflow)))
    return kept


def stacked_percentages(totals: Sequence[int]) -> list[int]:
    """Convert raw totals to whole percentages that always sum to exactly 100 (or all 0).

    The last entry absorbs the rounding remainder so the segments of a
    100%-stacked bar always tile exactly, regardless of how individual
    shares round.
    """
    grand_total = sum(totals)
    if grand_total == 0:
        return [0 for _ in totals]

    percentages: list[int] = []
    running = 0
    last_index = len(totals) - 1
    for index, total in enumerate(totals):
        if index == last_index:
            percentages.append(100 - running)
        else:
            share = round(total / grand_total * 100)
            running += share
            percentages.append(share)
    return percentages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/render/test_plotly.py -v`
Expected: all tests PASS, including the pre-existing ones (`render_usage_bar_chart` is untouched in this task).

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/render/plotly.py tests/render/test_plotly.py
git commit -m "feat: add bucket_top_n and stacked_percentages chart helpers"
```

---

### Task 2: Replace the Skills/MCP bar chart with a capped pie chart

**Files:**
- Modify: `src/agent_usage/render/plotly.py`
- Test: `tests/render/test_plotly.py`

**Interfaces:**
- Consumes: `rank_usage` and `bucket_top_n` from Task 1.
- Produces: `render_usage_pie_chart(*, title: str, counters: Mapping[str, int], top_n: int) -> bytes`, replacing `render_usage_bar_chart` (deleted). Consumed by Task 5.
- Also changes `_base_layout` and `_to_static_png` (internal helpers) to support a chart-specific width — `render_agent_share_bar` in Task 3 relies on `_base_layout`'s new `width` parameter defaulting to `CHART_WIDTH`.

- [ ] **Step 1: Write the failing tests**

In `tests/render/test_plotly.py`, replace the existing bar-chart test and import:

Remove this import line:
```python
    render_usage_bar_chart,
```
from the `from agent_usage.render.plotly import (...)` block, and add `render_usage_pie_chart` in its place (alphabetically, after `render_stacked_token_chart`):

```python
from agent_usage.render.plotly import (
    bucket_top_n,
    rank_usage,
    render_stacked_token_chart,
    render_usage_pie_chart,
    stacked_percentages,
)
```

Remove this test entirely:
```python
def test_render_usage_bar_chart_handles_no_observed_usage() -> None:
    image = render_usage_bar_chart(title="Skills", counters={})

    assert image.startswith(_PNG_SIGNATURE)
```

Replace it with:
```python
def test_render_usage_pie_chart_handles_no_observed_usage() -> None:
    image = render_usage_pie_chart(title="Skills", counters={}, top_n=6)

    assert image.startswith(_PNG_SIGNATURE)


def test_render_usage_pie_chart_renders_within_the_cap() -> None:
    image = render_usage_pie_chart(
        title="Skills", counters={"alpha": 5, "beta": 3}, top_n=6
    )

    assert image.startswith(_PNG_SIGNATURE)


def test_render_usage_pie_chart_renders_with_overflow_bucketed() -> None:
    counters = {f"skill-{i}": 10 - i for i in range(10)}

    image = render_usage_pie_chart(title="Skills", counters=counters, top_n=6)

    assert image.startswith(_PNG_SIGNATURE)


def test_render_usage_pie_chart_is_deterministic() -> None:
    counters = {"alpha": 5, "beta": 3, "gamma": 1}

    first = render_usage_pie_chart(title="Skills", counters=counters, top_n=2)
    second = render_usage_pie_chart(title="Skills", counters=counters, top_n=2)

    assert first == second
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/render/test_plotly.py -v`
Expected: `ImportError: cannot import name 'render_usage_pie_chart'`.

- [ ] **Step 3: Implement `render_usage_pie_chart`, delete `render_usage_bar_chart`**

In `src/agent_usage/render/plotly.py`:

Change `_base_layout` (currently takes only `title` and `height`) to accept an optional `width`:

```python
def _base_layout(*, title: str, height: int, width: int = CHART_WIDTH) -> dict:
    return {
        "width": width,
        "height": height,
        "paper_bgcolor": _BACKGROUND,
        "plot_bgcolor": _BACKGROUND,
        "font": {"family": "Arial, sans-serif", "color": _TEXT, "size": 13},
        "title": {"text": title, "x": 0, "xanchor": "left", "font": {"size": 18}},
        "margin": {"l": 76, "r": 36, "t": 60, "b": 72},
    }
```

Change `_to_static_png` to size the export from the figure's own layout width instead of the module-level constant, so narrower charts (the pie charts) actually export narrower:

```python
def _to_static_png(figure: go.Figure) -> bytes:
    """Export a high-resolution PNG that can be embedded in a README reliably."""
    return pio.to_image(
        figure,
        format="png",
        width=figure.layout.width,
        height=figure.layout.height,
        scale=2,
    )
```

Shrink the token line chart height (part of the spec's "Sizing changes to existing charts"):

```python
_TOKEN_CHART_HEIGHT = 300
```
(was `390`)

Delete `_MIN_USAGE_CHART_HEIGHT`, `_USAGE_ROW_HEIGHT`, and `_USAGE` (the bar chart's height/color constants — no longer used by anything after this task).

Add new constants near the other color constants:

```python
_PIE_CHART_WIDTH = 460
_PIE_CHART_HEIGHT = 340
_PIE_MARGIN = {"l": 12, "r": 150, "t": 48, "b": 12}
_PIE_COLORS = (
    "#2563eb",
    "#14b8a6",
    "#a855f7",
    "#f59e0b",
    "#ef4444",
    "#0ea5e9",
    "#84cc16",
    "#ec4899",
)
_OTHER_COLOR = "#9ca3af"
```

Delete the entire `render_usage_bar_chart` function and replace it with:

```python
def render_usage_pie_chart(*, title: str, counters: Mapping[str, int], top_n: int) -> bytes:
    """Render Skill or MCP counts as a pie chart capped at ``top_n`` slices plus 'Other'."""
    ranked = rank_usage(counters)
    if not ranked:
        usage_kind = "skill" if title.lower() == "skills" else title.lower()
        figure = go.Figure()
        figure.add_annotation(
            text=f"No {usage_kind} activity observed yet.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 16, "color": _AXIS},
        )
        figure.update_layout(
            **_base_layout(title=title, height=_PIE_CHART_HEIGHT, width=_PIE_CHART_WIDTH)
        )
        figure.update_xaxes(visible=False, fixedrange=True)
        figure.update_yaxes(visible=False, fixedrange=True)
        return _to_static_png(figure)

    slices = bucket_top_n(ranked, top_n)
    names, counts = zip(*slices, strict=True)
    colors = list(_PIE_COLORS[: len(names)])
    if names[-1] == _OTHER_LABEL:
        colors[-1] = _OTHER_COLOR

    figure = go.Figure(
        go.Pie(
            labels=names,
            values=counts,
            textinfo="percent",
            marker={"colors": colors},
            hovertemplate="%{label}<br>%{value:,} calls<extra></extra>",
        )
    )
    figure.update_layout(
        **_base_layout(title=title, height=_PIE_CHART_HEIGHT, width=_PIE_CHART_WIDTH),
        legend={"orientation": "v", "x": 1.02, "y": 0.5, "yanchor": "middle"},
    )
    figure.update_layout(margin=_PIE_MARGIN)
    return _to_static_png(figure)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/render/test_plotly.py -v`
Expected: all tests PASS, including `test_render_stacked_token_chart_produces_a_github_safe_png` and `test_plotly_png_rendering_is_deterministic` (unaffected by the `_base_layout`/`_to_static_png` signature changes since both pass `width=CHART_WIDTH` implicitly via the default).

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/render/plotly.py tests/render/test_plotly.py
git commit -m "feat: replace Skills/MCP bar chart with a top-N pie chart"
```

---

### Task 3: New chart — agent usage-share bar

**Files:**
- Modify: `src/agent_usage/render/plotly.py`
- Test: `tests/render/test_plotly.py`

**Interfaces:**
- Consumes: `stacked_percentages` from Task 1; `_base_layout`, `_to_static_png`, `_AXIS` (existing internals, now width-aware from Task 2).
- Produces: `render_agent_share_bar(*, agent_totals: Mapping[str, Mapping[str, int]]) -> bytes`. Consumed by Task 5. `agent_totals` is expected in the shape `aggregate_records()["agents"]` already produces — a dict keyed by `"hermes_agent"` / `"claude_code"` / `"codex"`, each value a dict with at least a `"headline_total"` int key.

- [ ] **Step 1: Write the failing tests**

Add `render_agent_share_bar` to the import block in `tests/render/test_plotly.py`:

```python
from agent_usage.render.plotly import (
    bucket_top_n,
    rank_usage,
    render_agent_share_bar,
    render_stacked_token_chart,
    render_usage_pie_chart,
    stacked_percentages,
)
```

Append these tests:

```python
def test_render_agent_share_bar_handles_no_activity() -> None:
    image = render_agent_share_bar(
        agent_totals={
            "hermes_agent": {"headline_total": 0},
            "claude_code": {"headline_total": 0},
            "codex": {"headline_total": 0},
        }
    )

    assert image.startswith(_PNG_SIGNATURE)


def test_render_agent_share_bar_handles_missing_agent_keys() -> None:
    image = render_agent_share_bar(agent_totals={})

    assert image.startswith(_PNG_SIGNATURE)


def test_render_agent_share_bar_renders_with_activity() -> None:
    image = render_agent_share_bar(
        agent_totals={
            "hermes_agent": {"headline_total": 100},
            "claude_code": {"headline_total": 300},
            "codex": {"headline_total": 0},
        }
    )

    assert image.startswith(_PNG_SIGNATURE)


def test_render_agent_share_bar_is_deterministic() -> None:
    agent_totals = {
        "hermes_agent": {"headline_total": 100},
        "claude_code": {"headline_total": 300},
        "codex": {"headline_total": 50},
    }

    first = render_agent_share_bar(agent_totals=agent_totals)
    second = render_agent_share_bar(agent_totals=agent_totals)

    assert first == second
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/render/test_plotly.py -v`
Expected: `ImportError: cannot import name 'render_agent_share_bar'`.

- [ ] **Step 3: Implement `render_agent_share_bar`**

In `src/agent_usage/render/plotly.py`, add near the other chart constants:

```python
_AGENT_BAR_HEIGHT = 150
_AGENT_BAR_MARGIN = {"l": 12, "r": 24, "t": 48, "b": 12}
_AGENT_SERIES = (
    ("hermes_agent", "Hermes", "#f59e0b"),
    ("claude_code", "Claude Code", "#d97757"),
    ("codex", "Codex", "#10a37f"),
)
```

Add the function at the end of the file:

```python
def render_agent_share_bar(*, agent_totals: Mapping[str, Mapping[str, int]]) -> bytes:
    """Render each agent's share of lifetime tokens as a single 100%-stacked bar."""
    totals = [
        agent_totals.get(key, {}).get("headline_total", 0) for key, _, _ in _AGENT_SERIES
    ]

    if sum(totals) == 0:
        figure = go.Figure()
        figure.add_annotation(
            text="No agent activity observed yet.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 16, "color": _AXIS},
        )
        figure.update_layout(**_base_layout(title="Agent Share", height=_AGENT_BAR_HEIGHT))
        figure.update_xaxes(visible=False, fixedrange=True)
        figure.update_yaxes(visible=False, fixedrange=True)
        return _to_static_png(figure)

    percentages = stacked_percentages(totals)
    figure = go.Figure()
    for (_, label, color), percentage in zip(_AGENT_SERIES, percentages, strict=True):
        figure.add_trace(
            go.Bar(
                x=[percentage],
                y=[""],
                orientation="h",
                name=label,
                marker={"color": color},
                text=f"{label}: {percentage}%",
                textposition="inside",
                insidetextanchor="middle",
                hovertemplate=f"{label}<br>%{{x}}%<extra></extra>",
            )
        )
    figure.update_layout(
        **_base_layout(title="Agent Share", height=_AGENT_BAR_HEIGHT),
        barmode="stack",
        showlegend=False,
    )
    figure.update_layout(margin=_AGENT_BAR_MARGIN)
    figure.update_xaxes(visible=False, range=[0, 100], fixedrange=True)
    figure.update_yaxes(visible=False, fixedrange=True)
    return _to_static_png(figure)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/render/test_plotly.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/render/plotly.py tests/render/test_plotly.py
git commit -m "feat: add render_agent_share_bar chart"
```

---

### Task 4: Trim the markdown layout and thread the new chart through `render_dashboard`

**Files:**
- Modify: `src/agent_usage/render/markdown.py`
- Test: `tests/render/test_markdown.py`

**Interfaces:**
- Consumes: `render_usage_pie_chart` and `render_agent_share_bar` from Tasks 2 and 3.
- Produces:
  - `render_dashboard_markdown(*, rolling_chart_path=..., total_chart_path=..., agent_share_chart_path=..., skills_chart_path=..., mcp_chart_path=...) -> str`
  - `render_dashboard(payloads, *, today, generated_at, rolling_chart_path=..., total_chart_path=..., agent_share_chart_path=..., skills_chart_path=..., mcp_chart_path=..., pie_top_n: int = 6) -> dict` with `dict["charts"]` now containing an `"agent_share"` key alongside `"rolling"`, `"total"`, `"skills"`, `"mcp"`.
  Consumed by Task 5 (`commands/render.py`) and by `scripts/build_profile_dashboard.py` (Task 7).

- [ ] **Step 1: Write the failing test**

Replace `test_render_dashboard_produces_only_the_requested_readme_sections_and_plotly_svgs` in `tests/render/test_markdown.py` with:

```python
def test_render_dashboard_produces_only_the_requested_readme_sections_and_plotly_svgs() -> None:
    payloads = [_payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.CLAUDE_CODE)]

    result = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")

    assert result["markdown"].startswith(MARKER_START)
    assert result["markdown"].endswith(MARKER_END)
    assert result["markdown"].count(MARKER_START) == 1
    assert result["markdown"].count(MARKER_END) == 1
    assert "## Token Usage" in result["markdown"]
    assert "## Agent Share" in result["markdown"]
    assert "## Skill / MCP Usage" in result["markdown"]
    assert "### Rolling 14 Days Activity" not in result["markdown"]
    assert "## Total Activity" not in result["markdown"]
    assert "### Skills" not in result["markdown"]
    assert "### MCP" not in result["markdown"]
    assert "| ![Skill usage]" in result["markdown"]
    assert "| ![MCP usage]" in result["markdown"]
    assert "|---|---|" in result["markdown"]
    assert "Source Health" not in result["markdown"]
    assert "Last updated" not in result["markdown"]
    assert set(result["charts"]) == {"rolling", "total", "agent_share", "skills", "mcp"}
    for asset in result["charts"].values():
        assert asset.startswith(b"\x89PNG\r\n\x1a\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/render/test_markdown.py -v`
Expected: FAIL — `"## Agent Share" in result["markdown"]` is False against the current markdown output.

- [ ] **Step 3: Update `render_dashboard_markdown` and `render_dashboard`**

In `src/agent_usage/render/markdown.py`:

Change the import line:

```python
from agent_usage.render.plotly import (
    render_agent_share_bar,
    render_stacked_token_chart,
    render_usage_pie_chart,
)
```

Add a default path constant next to the existing four:

```python
_DEFAULT_AGENT_SHARE_CHART_PATH = "assets/agent-usage/agent-share.png"
```

Replace `render_dashboard_markdown` with:

```python
def render_dashboard_markdown(
    *,
    rolling_chart_path: str = _DEFAULT_ROLLING_CHART_PATH,
    total_chart_path: str = _DEFAULT_TOTAL_CHART_PATH,
    agent_share_chart_path: str = _DEFAULT_AGENT_SHARE_CHART_PATH,
    skills_chart_path: str = _DEFAULT_SKILLS_CHART_PATH,
    mcp_chart_path: str = _DEFAULT_MCP_CHART_PATH,
) -> str:
    """Render the managed dashboard section as a single Markdown string."""
    sections = [
        MARKER_START,
        "## Token Usage",
        "",
        f"![Rolling 14 days input, output, and reasoning token activity]({rolling_chart_path})",
        f"![Total input, output, and reasoning token activity]({total_chart_path})",
        "",
        "## Agent Share",
        "",
        f"![Agent usage share by lifetime tokens]({agent_share_chart_path})",
        "",
        "## Skill / MCP Usage",
        "",
        f"| ![Skill usage]({skills_chart_path}) | ![MCP usage]({mcp_chart_path}) |",
        "|---|---|",
        "",
        MARKER_END,
    ]
    return "\n".join(sections)
```

Replace `render_dashboard`'s signature and body:

```python
def render_dashboard(
    payloads: list[dict],
    *,
    today: date,
    generated_at: str,
    rolling_chart_path: str = _DEFAULT_ROLLING_CHART_PATH,
    total_chart_path: str = _DEFAULT_TOTAL_CHART_PATH,
    agent_share_chart_path: str = _DEFAULT_AGENT_SHARE_CHART_PATH,
    skills_chart_path: str = _DEFAULT_SKILLS_CHART_PATH,
    mcp_chart_path: str = _DEFAULT_MCP_CHART_PATH,
    pie_top_n: int = 6,
) -> dict:
    """Build the full dashboard: Markdown plus five static Plotly PNG charts.

    ``payloads`` should already be validated (see
    :func:`agent_usage.aggregate.validate_and_partition`). Pure function of
    its inputs: ``today`` must be supplied by the caller so the whole pipeline
    stays deterministic and testable. ``generated_at`` remains accepted for
    backwards-compatible callers but is intentionally not inserted into the
    minimal managed README section.
    """
    rolling_payloads = rolling_window(payloads, end=today, days=_ROLLING_WINDOW_DAYS)
    lifetime_summary = aggregate_records(payloads)

    rolling_daily = daily_token_totals(rolling_payloads)
    rolling_dates = [
        (today - timedelta(days=offset)).isoformat()
        for offset in range(_ROLLING_WINDOW_DAYS - 1, -1, -1)
    ]
    rolling_series = [(day, rolling_daily.get(day)) for day in rolling_dates]

    lifetime_daily = daily_token_totals(payloads)
    if lifetime_daily:
        first_day = min(date.fromisoformat(day) for day in lifetime_daily)
        total_dates = [
            (first_day + timedelta(days=offset)).isoformat()
            for offset in range((today - first_day).days + 1)
        ]
    else:
        total_dates = []
    total_series = [(day, lifetime_daily.get(day)) for day in total_dates]

    charts = {
        "rolling": render_stacked_token_chart(
            title="Rolling 14 Days Activity", series=rolling_series
        ),
        "total": render_stacked_token_chart(title="Total Activity", series=total_series),
        "agent_share": render_agent_share_bar(agent_totals=lifetime_summary["agents"]),
        "skills": render_usage_pie_chart(
            title="Skills", counters=lifetime_summary["skills"], top_n=pie_top_n
        ),
        "mcp": render_usage_pie_chart(
            title="MCP", counters=lifetime_summary["mcp_servers"], top_n=pie_top_n
        ),
    }

    markdown = render_dashboard_markdown(
        rolling_chart_path=rolling_chart_path,
        total_chart_path=total_chart_path,
        agent_share_chart_path=agent_share_chart_path,
        skills_chart_path=skills_chart_path,
        mcp_chart_path=mcp_chart_path,
    )

    return {"markdown": markdown, "charts": charts}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/render/test_markdown.py -v`
Expected: all tests PASS. (The other pre-existing tests in this file — `test_render_dashboard_is_deterministic_regardless_of_payload_order`, `test_render_dashboard_keeps_source_status_out_of_the_readme`, the `update_readme` tests — are unaffected by this change and should already pass.)

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/render/markdown.py tests/render/test_markdown.py
git commit -m "feat: trim dashboard markdown layout, add agent-share section"
```

---

### Task 5: Thread `pie_top_n` and the agent-share chart through the local preview command

**Files:**
- Modify: `src/agent_usage/commands/render.py`
- Test: `tests/commands/test_render.py`

**Interfaces:**
- Consumes: `render_dashboard(..., agent_share_chart_path=..., pie_top_n=...)` from Task 4.
- Produces: `render(*, ledger_path, output_dir, privacy_policy=PrivacyPolicy(), today, generated_at, pie_top_n: int = 6) -> RenderResult` (added `pie_top_n` parameter; `RenderResult` shape unchanged). Consumed by Task 6 (`cli.py`).

- [ ] **Step 1: Write the failing test**

Add to `tests/commands/test_render.py`:

```python
def test_render_writes_the_agent_share_chart(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(ledger_path)
    output_dir = tmp_path / "preview"

    result = render(
        ledger_path=ledger_path, output_dir=output_dir, today=TODAY, generated_at=GENERATED_AT
    )

    readme = result.readme_path.read_text(encoding="utf-8")
    assert "assets/agent-usage/agent-share.png" in readme
    assert (output_dir / "assets" / "agent-usage" / "agent-share.png").exists()


def test_render_honors_a_custom_pie_top_n(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(ledger_path)
    output_dir = tmp_path / "preview"

    result = render(
        ledger_path=ledger_path,
        output_dir=output_dir,
        today=TODAY,
        generated_at=GENERATED_AT,
        pie_top_n=1,
    )

    assert result.changed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_render.py -v`
Expected: `test_render_writes_the_agent_share_chart` FAILs (`assert "assets/agent-usage/agent-share.png" in readme` is False). `test_render_honors_a_custom_pie_top_n` FAILs with `TypeError: render() got an unexpected keyword argument 'pie_top_n'`.

- [ ] **Step 3: Update `commands/render.py`**

In `src/agent_usage/commands/render.py`, add the new path constant next to the existing four:

```python
_AGENT_SHARE_CHART_RELATIVE_PATH = Path("assets/agent-usage/agent-share.png")
```

Replace the `render` function signature and body:

```python
def render(
    *,
    ledger_path: Path,
    output_dir: Path,
    privacy_policy: PrivacyPolicy = PrivacyPolicy(),
    today: date,
    generated_at: str,
    pie_top_n: int = 6,
) -> RenderResult:
    """Regenerate this device's local dashboard preview. Returns whether anything changed."""
    repository = LedgerRepository.open(ledger_path)
    try:
        device_id = repository.get_or_create_device_id()
        records = repository.list_records()
    finally:
        repository.close()

    device_data_dir = output_dir / "data" / "v1" / "devices" / device_id
    payloads = stage_daily_records(
        device_data_dir, device_id=device_id, records=records, privacy_policy=privacy_policy
    )

    partition = validate_and_partition(
        [(device_id, payload) for payload in payloads], today=today
    )

    rolling_chart_path = output_dir / _ROLLING_CHART_RELATIVE_PATH
    total_chart_path = output_dir / _TOTAL_CHART_RELATIVE_PATH
    agent_share_chart_path = output_dir / _AGENT_SHARE_CHART_RELATIVE_PATH
    skills_chart_path = output_dir / _SKILLS_CHART_RELATIVE_PATH
    mcp_chart_path = output_dir / _MCP_CHART_RELATIVE_PATH
    dashboard = render_dashboard(
        partition.valid_payloads,
        today=today,
        generated_at=generated_at,
        rolling_chart_path=_ROLLING_CHART_RELATIVE_PATH.as_posix(),
        total_chart_path=_TOTAL_CHART_RELATIVE_PATH.as_posix(),
        agent_share_chart_path=_AGENT_SHARE_CHART_RELATIVE_PATH.as_posix(),
        skills_chart_path=_SKILLS_CHART_RELATIVE_PATH.as_posix(),
        mcp_chart_path=_MCP_CHART_RELATIVE_PATH.as_posix(),
        pie_top_n=pie_top_n,
    )

    readme_path = output_dir / "README.md"
    existing_readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    updated_readme = update_readme(existing_readme, dashboard["markdown"])

    changed = _write_if_changed(readme_path, updated_readme)
    for chart_path, chart in (
        (rolling_chart_path, dashboard["charts"]["rolling"]),
        (total_chart_path, dashboard["charts"]["total"]),
        (agent_share_chart_path, dashboard["charts"]["agent_share"]),
        (skills_chart_path, dashboard["charts"]["skills"]),
        (mcp_chart_path, dashboard["charts"]["mcp"]),
    ):
        changed = _write_if_changed(chart_path, chart) or changed

    return RenderResult(device_id=device_id, readme_path=readme_path, changed=changed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_render.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/commands/render.py tests/commands/test_render.py
git commit -m "feat: write the agent-share chart from the local preview command"
```

---

### Task 6: Add `--pie-top-n` to the `agent-usage render` CLI command

**Files:**
- Modify: `src/agent_usage/cli.py`
- Test: `tests/commands/test_cli.py`

**Interfaces:**
- Consumes: `render_command.render(..., pie_top_n=...)` from Task 5.
- Produces: a new `--pie-top-n` option on the `render` Typer command, exit code `2` (Typer's usage-error exit code) with a message containing `"pie-top-n"` when given a value below 1.

- [ ] **Step 1: Write the failing tests**

Add to `tests/commands/test_cli.py`, near `test_collect_then_render_produces_a_local_preview`:

```python
def test_render_accepts_a_custom_pie_top_n(tmp_path, monkeypatch) -> None:
    _patch_local_paths(monkeypatch, tmp_path)
    _patch_missing_sources(monkeypatch, tmp_path)

    runner.invoke(app, ["collect"])
    output_dir = tmp_path / "preview"

    result = runner.invoke(app, ["render", "--output-dir", str(output_dir), "--pie-top-n", "3"])

    assert result.exit_code == 0
    assert (output_dir / "README.md").exists()


def test_render_rejects_a_pie_top_n_below_one(tmp_path, monkeypatch) -> None:
    _patch_local_paths(monkeypatch, tmp_path)
    _patch_missing_sources(monkeypatch, tmp_path)

    output_dir = tmp_path / "preview"
    result = runner.invoke(app, ["render", "--output-dir", str(output_dir), "--pie-top-n", "0"])

    assert result.exit_code != 0
    assert "pie-top-n" in result.stdout.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_cli.py -v`
Expected: `test_render_accepts_a_custom_pie_top_n` FAILs with `No such option: --pie-top-n`. `test_render_rejects_a_pie_top_n_below_one` FAILs the same way.

- [ ] **Step 3: Add the option**

In `src/agent_usage/cli.py`, replace the `render` command:

```python
@app.command()
def render(
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Where to write the local dashboard preview."
    ),
    pie_top_n: int = typer.Option(
        6,
        "--pie-top-n",
        help="Max Skills/MCP pie slices to show before bucketing the rest into 'Other'.",
    ),
) -> None:
    """Render a local preview of the dashboard from this device's own collected data."""
    if pie_top_n < 1:
        raise typer.BadParameter("--pie-top-n must be at least 1")
    now = datetime.now(timezone.utc)
    config = load_config(config_file_path())
    resolved_output_dir = output_dir or (ledger_file_path().parent / "preview")
    result = render_command.render(
        ledger_path=ledger_file_path(),
        output_dir=resolved_output_dir,
        privacy_policy=PrivacyPolicy.from_config(config),
        today=now.date(),
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        pie_top_n=pie_top_n,
    )
    typer.echo(f"agent-usage: preview written to {result.readme_path}")
    typer.echo(
        "agent-usage: dashboard changed" if result.changed else "agent-usage: dashboard unchanged"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_cli.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/cli.py tests/commands/test_cli.py
git commit -m "feat: add --pie-top-n option to the render CLI command"
```

---

### Task 7: Thread the agent-share chart and `--pie-top-n` through the profile-repo build script

**Files:**
- Modify: `scripts/build_profile_dashboard.py`

This script has no existing pytest coverage (it's explicitly "not part of the installable `agent_usage` package" — meant to be checked out and run directly in the profile repo's CI, per its module docstring). This task follows that existing pattern and verifies with a manual smoke run instead of adding new pytest infrastructure for a file nothing else in the repo tests.

**Interfaces:**
- Consumes: `render_dashboard(..., agent_share_chart_path=..., pie_top_n=...)` from Task 4.
- Produces: `build(..., agent_share_chart_path: Path | None = None, pie_top_n: int = 6) -> bool` (same return type as today); a new `--agent-share-chart` and `--pie-top-n` CLI argument on `main()`.

- [ ] **Step 1: Update `build()`**

In `scripts/build_profile_dashboard.py`, add a default path constant next to the existing four:

```python
DEFAULT_AGENT_SHARE_CHART = Path("assets/agent-usage/agent-share.png")
```

Replace the `build` function signature and body:

```python
def build(
    *,
    data_dir: Path,
    readme_path: Path,
    rolling_chart_path: Path,
    total_chart_path: Path | None = None,
    agent_share_chart_path: Path | None = None,
    skills_chart_path: Path | None = None,
    mcp_chart_path: Path | None = None,
    lifetime_chart_path: Path | None = None,
    pie_top_n: int = 6,
    today: date,
    generated_at: str,
) -> bool:
    """Regenerate the README and chart assets. Returns True if anything changed."""
    if total_chart_path is None:
        if lifetime_chart_path is None:
            raise ValueError("total_chart_path is required")
        total_chart_path = lifetime_chart_path.with_suffix(".png")
    chart_dir = total_chart_path.parent
    agent_share_chart_path = agent_share_chart_path or chart_dir / DEFAULT_AGENT_SHARE_CHART.name
    skills_chart_path = skills_chart_path or chart_dir / DEFAULT_SKILLS_CHART.name
    mcp_chart_path = mcp_chart_path or chart_dir / DEFAULT_MCP_CHART.name

    entries = _load_entries(data_dir)
    partition = validate_and_partition(entries, today=today)
    for issue in partition.issues:
        print(
            f"agent-usage: skipping invalid record "
            f"device={issue.device_id} date={issue.date} reason={issue.reason}",
            file=sys.stderr,
        )

    dashboard = render_dashboard(
        partition.valid_payloads,
        today=today,
        generated_at=generated_at,
        rolling_chart_path=_readme_relative_path(rolling_chart_path, readme_path=readme_path),
        total_chart_path=_readme_relative_path(total_chart_path, readme_path=readme_path),
        agent_share_chart_path=_readme_relative_path(
            agent_share_chart_path, readme_path=readme_path
        ),
        skills_chart_path=_readme_relative_path(skills_chart_path, readme_path=readme_path),
        mcp_chart_path=_readme_relative_path(mcp_chart_path, readme_path=readme_path),
        pie_top_n=pie_top_n,
    )

    existing_readme = (
        readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    )
    updated_readme = update_readme(existing_readme, dashboard["markdown"])

    changed = _write_if_changed(readme_path, updated_readme)
    for chart_path, chart in (
        (rolling_chart_path, dashboard["charts"]["rolling"]),
        (total_chart_path, dashboard["charts"]["total"]),
        (agent_share_chart_path, dashboard["charts"]["agent_share"]),
        (skills_chart_path, dashboard["charts"]["skills"]),
        (mcp_chart_path, dashboard["charts"]["mcp"]),
    ):
        changed = _write_if_changed(chart_path, chart) or changed
    return changed
```

- [ ] **Step 2: Update `_parse_args` and `main`**

Add to `_parse_args`, next to the existing `--skills-chart`/`--mcp-chart` arguments:

```python
    parser.add_argument("--agent-share-chart", type=Path, default=DEFAULT_AGENT_SHARE_CHART)
    parser.add_argument("--pie-top-n", type=int, default=6)
```

In `main()`, add alongside the existing `skills_chart_path`/`mcp_chart_path` resolution block:

```python
    agent_share_chart_path = (
        default_chart_dir / DEFAULT_AGENT_SHARE_CHART.name
        if args.agent_share_chart == DEFAULT_AGENT_SHARE_CHART
        else args.agent_share_chart
    )
```

Update the `build(...)` call inside `main()` to pass the two new values:

```python
    changed = build(
        data_dir=args.data_dir,
        readme_path=args.readme,
        rolling_chart_path=rolling_chart_path,
        total_chart_path=total_chart_path if args.lifetime_chart is None else None,
        agent_share_chart_path=agent_share_chart_path,
        skills_chart_path=skills_chart_path,
        mcp_chart_path=mcp_chart_path,
        lifetime_chart_path=args.lifetime_chart,
        pie_top_n=args.pie_top_n,
        today=today,
        generated_at=generated_at,
    )
```

- [ ] **Step 3: Manual smoke test**

Run against the repo's own preview fixture data to confirm the script still runs end-to-end and now writes the agent-share chart:

```bash
uv run python scripts/build_profile_dashboard.py \
  --data-dir agent-usage-preview/data/v1/devices \
  --readme /tmp/smoke-readme/README.md \
  --rolling-chart assets/agent-usage/token-activity-14d.png \
  --total-chart assets/agent-usage/token-activity-total.png \
  --agent-share-chart assets/agent-usage/agent-share.png \
  --skills-chart assets/agent-usage/skills.png \
  --mcp-chart assets/agent-usage/mcp.png \
  --pie-top-n 4 \
  --today 2026-07-21
```

Expected: prints `agent-usage: dashboard changed`; `/tmp/smoke-readme/assets/agent-usage/agent-share.png` exists and is a valid PNG (`file /tmp/smoke-readme/assets/agent-usage/agent-share.png` reports `PNG image data`); `/tmp/smoke-readme/README.md` contains `## Agent Share` and a markdown table row for Skills/MCP.

Clean up the scratch output afterward: `rm -rf /tmp/smoke-readme`.

- [ ] **Step 4: Commit**

```bash
git add scripts/build_profile_dashboard.py
git commit -m "feat: thread pie-top-n and the agent-share chart through the CI build script"
```

---

### Task 8: Full-suite verification and preview regeneration

**Files:**
- None modified — verification only, plus regenerating the committed preview assets.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS, zero failures.

- [ ] **Step 2: Run lint**

Run: `uv run ruff check src tests scripts`
Expected: no errors. Fix anything ruff flags (e.g. unused imports left over from removing `render_usage_bar_chart`) and re-run until clean.

- [ ] **Step 3: Regenerate the local preview and eyeball it**

```bash
uv run agent-usage render --output-dir agent-usage-preview
```

Open `agent-usage-preview/assets/agent-usage/skills.png`, `mcp.png`, and `agent-share.png` and confirm: the Skills pie has at most 7 slices (6 + Other) if more than 6 skills were observed, the MCP pie renders the same way, and the agent-share bar shows a single 100%-wide stacked bar with percentage labels. Confirm `agent-usage-preview/README.md` matches the new layout from Task 4's test (`## Agent Share`, no `### Skills`/`### MCP` subheadings, Skills/MCP in a two-column table).

- [ ] **Step 4: Commit the regenerated preview assets**

```bash
git add agent-usage-preview
git commit -m "chore: regenerate dashboard preview with the compact layout"
```

## Self-Review Notes

- **Spec coverage:** pie chart + top-N cap (Task 2), CLI-adjustable top-N (Task 6, Task 7), agent-share bar with lifetime scope and fixed order (Task 3), trimmed headings + side-by-side Skills/MCP table (Task 4), shrunk chart heights (Task 2's `_TOKEN_CHART_HEIGHT` change, Task 2/3's pie/bar-specific compact sizing) — all covered.
- **Type consistency:** `agent_totals` is `Mapping[str, Mapping[str, int]]` consistently across `render_agent_share_bar` (Task 3) and its caller in `render_dashboard` (Task 4), matching `aggregate_records()["agents"]`'s actual shape (`dict[str, dict]` with a `headline_total` int key, per `src/agent_usage/aggregate.py`). `pie_top_n: int` is consistent from the Typer option (Task 6) through `commands/render.py` (Task 5) to `render_dashboard` (Task 4) to `render_usage_pie_chart` (Task 2).
- **No placeholders:** every step above has complete, real code — no TBDs.
