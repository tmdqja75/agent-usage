"""Renders the managed README dashboard section as Markdown.

Consumes the aggregated summaries from :mod:`agent_usage.aggregate` and
produces a self-contained Markdown block bounded by stable managed
markers, so an existing README's surrounding content is always preserved
on update. ``render_dashboard`` is the single entry point that ties
aggregation, Markdown rendering, and chart generation together; it is a
pure function of its inputs (``today`` and ``generated_at`` must be
supplied by the caller, never computed internally) so the whole pipeline
stays deterministic and testable.
"""

from __future__ import annotations

from datetime import date, timedelta

from agent_usage.aggregate import (
    aggregate_records,
    daily_totals,
    monthly_totals,
    rolling_window,
)
from agent_usage.models import SourceStatus, SupportedAgent
from agent_usage.render.svg import render_bar_chart, render_line_chart

MARKER_START = "<!-- agent-usage:start -->"
MARKER_END = "<!-- agent-usage:end -->"

_AGENT_ORDER = (
    SupportedAgent.HERMES_AGENT.value,
    SupportedAgent.CLAUDE_CODE.value,
    SupportedAgent.CODEX.value,
)
_AGENT_DISPLAY_NAMES = {
    SupportedAgent.HERMES_AGENT.value: "Hermes Agent",
    SupportedAgent.CLAUDE_CODE.value: "Claude Code",
    SupportedAgent.CODEX.value: "Codex",
}
_STATUS_DISPLAY = {
    SourceStatus.AVAILABLE_WITH_ACTIVITY.value: "Active",
    SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY.value: "Zero activity",
    SourceStatus.SOURCE_UNAVAILABLE.value: "Unavailable",
}

_ROLLING_WINDOW_DAYS = 14
_DEFAULT_ROLLING_CHART_PATH = "assets/agent-usage/rolling-14d.svg"
_DEFAULT_LIFETIME_CHART_PATH = "assets/agent-usage/lifetime.svg"


def _format_count(value: int) -> str:
    return f"{value:,}"


def render_source_health_table(summary: dict) -> str:
    lines = ["| Agent | Status |", "|---|---|"]
    for agent_key in _AGENT_ORDER:
        status = summary["agents"][agent_key]["source_status"]
        lines.append(f"| {_AGENT_DISPLAY_NAMES[agent_key]} | {_STATUS_DISPLAY[status]} |")
    return "\n".join(lines)


def render_rolling_totals_table(summary: dict) -> str:
    agents = summary["agents"].values()
    lines = [
        "| Metric | Value |",
        "|---|---|",
        f"| Input tokens | {_format_count(sum(a['input_tokens'] for a in agents))} |",
        f"| Output tokens | {_format_count(sum(a['output_tokens'] for a in agents))} |",
        f"| Reasoning tokens | {_format_count(sum(a['reasoning_tokens'] for a in agents))} |",
        f"| Sessions | {_format_count(sum(a['session_count'] for a in agents))} |",
        f"| Active days | {summary['active_days']} |",
        f"| Distinct skills | {len(summary['skills'])} |",
        f"| Distinct MCP servers | {len(summary['mcp_servers'])} |",
    ]
    return "\n".join(lines)


def render_agent_comparison_table(summary: dict) -> str:
    lines = [
        "| Agent | Input | Output | Reasoning | Sessions | Active days |",
        "|---|---|---|---|---|---|",
    ]
    for agent_key in _AGENT_ORDER:
        agent = summary["agents"][agent_key]
        lines.append(
            f"| {_AGENT_DISPLAY_NAMES[agent_key]} | {_format_count(agent['input_tokens'])} | "
            f"{_format_count(agent['output_tokens'])} | {_format_count(agent['reasoning_tokens'])} | "
            f"{_format_count(agent['session_count'])} | {agent['active_days']} |"
        )
    return "\n".join(lines)


def render_leaderboard_table(counters: dict, *, header: str, top_n: int = 10) -> str:
    if not counters:
        return f"_No {header.lower()} activity observed yet._"
    ranked = sorted(counters.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    lines = [f"| {header} | Calls |", "|---|---|"]
    for name, count in ranked:
        lines.append(f"| {name} | {_format_count(count)} |")
    return "\n".join(lines)


def render_dashboard_markdown(
    *,
    rolling_summary: dict,
    lifetime_summary: dict,
    generated_at: str,
    rolling_chart_path: str = _DEFAULT_ROLLING_CHART_PATH,
    lifetime_chart_path: str = _DEFAULT_LIFETIME_CHART_PATH,
) -> str:
    """Render the managed dashboard section as a single Markdown string."""
    sections = [
        MARKER_START,
        "## Agent Usage",
        "",
        f"_Last updated: {generated_at}_",
        "",
        "### Source Health",
        render_source_health_table(rolling_summary),
        "",
        "### Rolling 14-Day Totals",
        render_rolling_totals_table(rolling_summary),
        "",
        f"![14-day token activity]({rolling_chart_path})",
        "",
        "### Per-Agent Comparison (rolling 14 days)",
        render_agent_comparison_table(rolling_summary),
        "",
        "### Lifetime Totals",
        render_agent_comparison_table(lifetime_summary),
        "",
        f"![Monthly token activity]({lifetime_chart_path})",
        "",
        "### Top Skills (rolling 14 days)",
        render_leaderboard_table(rolling_summary["skills"], header="Skill"),
        "",
        "### Top MCP Servers (rolling 14 days)",
        render_leaderboard_table(rolling_summary["mcp_servers"], header="MCP Server"),
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
    lifetime_chart_path: str = _DEFAULT_LIFETIME_CHART_PATH,
) -> dict:
    """Build the full dashboard: managed Markdown plus both SVG charts.

    ``payloads`` should already be validated (see
    :func:`agent_usage.aggregate.validate_and_partition`). Pure function of
    its inputs: ``today`` and ``generated_at`` must be supplied by the
    caller so the whole pipeline stays deterministic and testable.
    """
    rolling_payloads = rolling_window(payloads, end=today, days=_ROLLING_WINDOW_DAYS)
    rolling_summary = aggregate_records(rolling_payloads)
    lifetime_summary = aggregate_records(payloads)

    daily = daily_totals(rolling_payloads)
    rolling_dates = [
        (today - timedelta(days=offset)).isoformat()
        for offset in range(_ROLLING_WINDOW_DAYS - 1, -1, -1)
    ]
    rolling_series = [(day, daily.get(day)) for day in rolling_dates]

    monthly = monthly_totals(payloads)
    monthly_series = [(month, total) for month, total in sorted(monthly.items())]

    rolling_svg = render_line_chart(title="14-Day Token Activity", series=rolling_series)
    lifetime_svg = render_bar_chart(title="Monthly Token Activity", series=monthly_series)

    markdown = render_dashboard_markdown(
        rolling_summary=rolling_summary,
        lifetime_summary=lifetime_summary,
        generated_at=generated_at,
        rolling_chart_path=rolling_chart_path,
        lifetime_chart_path=lifetime_chart_path,
    )

    return {"markdown": markdown, "rolling_svg": rolling_svg, "lifetime_svg": lifetime_svg}
