"""Tests for deterministic Plotly PNG chart generation."""

from __future__ import annotations

from agent_usage.render.plotly import (
    bucket_top_n,
    rank_usage,
    render_stacked_token_chart,
    render_usage_pie_chart,
    stacked_percentages,
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
