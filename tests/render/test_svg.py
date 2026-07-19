"""Tests for deterministic static SVG chart generation."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from agent_usage.render.svg import render_bar_chart, render_line_chart


def _assert_valid_svg(svg: str) -> None:
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")


def test_render_line_chart_produces_valid_xml() -> None:
    svg = render_line_chart(title="14-Day Activity", series=[("2026-07-01", 100), ("2026-07-02", 200)])

    _assert_valid_svg(svg)


def test_render_line_chart_is_deterministic() -> None:
    series = [("2026-07-01", 100), ("2026-07-02", 250), ("2026-07-03", 90)]

    first = render_line_chart(title="14-Day Activity", series=series)
    second = render_line_chart(title="14-Day Activity", series=series)

    assert first == second


def test_render_line_chart_handles_empty_series() -> None:
    svg = render_line_chart(title="14-Day Activity", series=[])

    _assert_valid_svg(svg)


def test_render_line_chart_breaks_the_path_across_missing_days() -> None:
    # None marks "no data" for that point -- must never be plotted as zero.
    # Two points on each side of the gap so each segment can form a real line.
    svg = render_line_chart(
        title="14-Day Activity",
        series=[
            ("2026-07-01", 100),
            ("2026-07-02", 120),
            ("2026-07-03", None),
            ("2026-07-04", 90),
            ("2026-07-05", 110),
        ],
    )

    _assert_valid_svg(svg)
    # Two distinct path segments (one before the gap, one after) rather than
    # a single path that would visually connect through the missing day.
    assert svg.count("<path") == 2


def test_render_line_chart_handles_all_missing_series() -> None:
    svg = render_line_chart(title="14-Day Activity", series=[("2026-07-01", None), ("2026-07-02", None)])

    _assert_valid_svg(svg)
    assert "<path" not in svg


def test_render_line_chart_labels_the_final_value() -> None:
    svg = render_line_chart(title="14-Day Activity", series=[("2026-07-01", 1234), ("2026-07-02", 5678)])

    assert "5,678" in svg


def test_render_line_chart_does_not_overflow_the_viewbox_on_the_right() -> None:
    svg = render_line_chart(title="14-Day Activity", series=[("2026-07-01", 999999999)])

    root = ET.fromstring(svg)
    _, _, width, _ = (float(v) for v in root.attrib["viewBox"].split())
    for text in root.iter():
        if text.tag.endswith("text") and text.attrib.get("text-anchor") != "end":
            x = float(text.attrib.get("x", 0))
            assert x <= width


def test_render_bar_chart_produces_valid_xml() -> None:
    svg = render_bar_chart(title="Monthly Trend", series=[("2026-06", 1000), ("2026-07", 2000)])

    _assert_valid_svg(svg)


def test_render_bar_chart_is_deterministic() -> None:
    series = [("2026-05", 500), ("2026-06", 1500), ("2026-07", 900)]

    first = render_bar_chart(title="Monthly Trend", series=series)
    second = render_bar_chart(title="Monthly Trend", series=series)

    assert first == second


def test_render_bar_chart_handles_empty_series() -> None:
    svg = render_bar_chart(title="Monthly Trend", series=[])

    _assert_valid_svg(svg)


def test_render_bar_chart_omits_bars_for_missing_months() -> None:
    svg = render_bar_chart(title="Monthly Trend", series=[("2026-06", None), ("2026-07", 500)])

    _assert_valid_svg(svg)
    assert svg.count('<path d="M') == 1


def test_render_bar_chart_labels_the_last_bar() -> None:
    svg = render_bar_chart(title="Monthly Trend", series=[("2026-06", 1000), ("2026-07", 4321)])

    assert "4,321" in svg
