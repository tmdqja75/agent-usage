"""Tests for deterministic Plotly PNG chart generation."""

from __future__ import annotations

from agent_usage.render.plotly import (
    rank_usage,
    render_stacked_token_chart,
    render_usage_bar_chart,
)


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_render_stacked_token_chart_produces_a_github_safe_png() -> None:
    image = render_stacked_token_chart(
        title="Rolling 14 Days Activity",
        series=[
            ("2026-07-01", {"input": 100, "output": 50, "reasoning": 25}),
            ("2026-07-02", {"input": 120, "output": 70, "reasoning": 30}),
        ],
    )

    assert image.startswith(_PNG_SIGNATURE)


def test_plotly_png_rendering_is_deterministic() -> None:
    series = [("2026-07-01", {"input": 100, "output": 50, "reasoning": 25})]

    first = render_stacked_token_chart(title="Total Activity", series=series)
    second = render_stacked_token_chart(title="Total Activity", series=series)

    assert first == second


def test_rank_usage_orders_most_used_first_then_name() -> None:
    ranked = rank_usage({"zeta": 3, "alpha": 3, "least": 1})

    assert ranked == [("alpha", 3), ("zeta", 3), ("least", 1)]


def test_render_usage_bar_chart_handles_no_observed_usage() -> None:
    image = render_usage_bar_chart(title="Skills", counters={})

    assert image.startswith(_PNG_SIGNATURE)
