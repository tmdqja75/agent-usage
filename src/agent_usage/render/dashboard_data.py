"""Build the chart-ready ``data.json`` payload consumed by the interactive dashboard UI.

Pure and I/O-free: takes already-validated daily payloads from
``validate_and_partition(...).valid_payloads`` and reshapes them into the exact
JSON contract the React charts expect.
"""

from __future__ import annotations

from datetime import date, timedelta

from agent_usage.aggregate import (
    aggregate_records,
    daily_agent_totals,
    daily_token_totals,
    daily_totals,
    rolling_window,
)
from agent_usage.models import SupportedAgent
from agent_usage.render._counters import bucket_top_n, rank_usage


def _pie(counters: dict[str, int], pie_top_n: int) -> list[dict]:
    return [
        {"name": name, "count": count}
        for name, count in bucket_top_n(rank_usage(counters), pie_top_n)
    ]


def build_dashboard_data(
    valid_payloads: list[dict],
    *,
    today: date,
    window_days: int = 14,
    pie_top_n: int = 6,
) -> dict:
    """Reshape validated daily payloads into the dashboard's data.json contract."""
    windowed = rolling_window(valid_payloads, end=today, days=window_days)
    token_by_date = daily_token_totals(windowed)

    tokens = [
        {
            "date": day,
            "input": totals["input"],
            "output": totals["output"],
            "reasoning": totals["reasoning"],
        }
        for day, totals in sorted(token_by_date.items())
        if totals is not None
    ]

    if tokens:
        window = {"start": tokens[0]["date"], "end": tokens[-1]["date"]}
    else:
        start = today - timedelta(days=window_days - 1)
        window = {"start": start.isoformat(), "end": today.isoformat()}

    aggregated = aggregate_records(valid_payloads)
    agents = [
        {"agent": agent.value, "tokens": aggregated["agents"][agent.value]["headline_total"]}
        for agent in SupportedAgent
    ]

    agent_totals_by_day = daily_agent_totals(valid_payloads)
    heatmap = [
        {
            "date": day,
            "tokens": total,
            "byAgent": [
                {"agent": agent_name, "tokens": agent_total}
                for agent_name, agent_total in sorted(
                    agent_totals_by_day.get(day, {}).items(), key=lambda kv: -kv[1]
                )
            ],
        }
        for day, total in sorted(daily_totals(valid_payloads).items())
    ]

    return {
        "window": window,
        "tokens": tokens,
        "agents": agents,
        "skills": _pie(aggregated["skills"], pie_top_n),
        "mcp": _pie(aggregated["mcp_servers"], pie_top_n),
        "heatmap": heatmap,
    }
