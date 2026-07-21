"""Renders the managed README dashboard section as Markdown.

Consumes the aggregated summaries from :mod:`agent_usage.aggregate` and
produces a self-contained Markdown block bounded by stable managed
markers, so an existing README's surrounding content is always preserved
on update. ``render_dashboard`` is the single entry point that ties
aggregation, Markdown rendering, and chart generation together; callers
supply ``today`` explicitly so the whole pipeline stays deterministic and
testable.
"""

from __future__ import annotations

from datetime import date, timedelta

from agent_usage.aggregate import aggregate_records, daily_token_totals, rolling_window
from agent_usage.render.plotly import (
    render_agent_share_bar,
    render_stacked_token_chart,
    render_usage_pie_chart,
)

MARKER_START = "<!-- agent-usage:start -->"
MARKER_END = "<!-- agent-usage:end -->"

_ROLLING_WINDOW_DAYS = 14
_DEFAULT_ROLLING_CHART_PATH = "assets/agent-usage/token-activity-14d.png"
_DEFAULT_TOTAL_CHART_PATH = "assets/agent-usage/token-activity-total.png"
_DEFAULT_AGENT_SHARE_CHART_PATH = "assets/agent-usage/agent-share.png"
_DEFAULT_SKILLS_CHART_PATH = "assets/agent-usage/skills.png"
_DEFAULT_MCP_CHART_PATH = "assets/agent-usage/mcp.png"


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


def update_readme(existing_readme: str, dashboard_markdown: str) -> str:
    """Replace content between the managed markers, preserving everything else.

    If no markers exist yet, appends a new managed section at the end.
    Idempotent: applying the same dashboard content twice leaves the
    README unchanged the second time.
    """
    start_index = existing_readme.find(MARKER_START)
    end_index = existing_readme.find(MARKER_END)
    if start_index == -1 or end_index == -1:
        if existing_readme.strip():
            return existing_readme.rstrip("\n") + "\n\n" + dashboard_markdown + "\n"
        return dashboard_markdown + "\n"

    end_index += len(MARKER_END)
    return existing_readme[:start_index] + dashboard_markdown + existing_readme[end_index:]


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
