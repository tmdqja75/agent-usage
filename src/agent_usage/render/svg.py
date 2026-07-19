"""Deterministic static SVG chart generation for the profile README dashboard.

Charts are plain, non-interactive SVG assets committed to the repo and
referenced by relative path from the README — no embedded scripts or
media-query theme switching, since GitHub's README image embedding
doesn't reliably support either. Each chart draws its own light
background (the validated dataviz reference palette's light surface) so
it stays readable regardless of the viewer's theme.

A ``None`` value in a series means "no data for this point" and is never
plotted as zero — the project's core distinction between
``source_unavailable`` and confirmed zero activity applies to chart data
too. A line chart breaks into separate path segments across a gap; a bar
chart simply omits the bar for that position.
"""

from __future__ import annotations

import math

# Validated default palette (agent-usage/dataviz reference palette.md).
SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES_BLUE = "#2a78d6"

WIDTH = 640
HEIGHT = 220
_PADDING_LEFT = 56
_PADDING_RIGHT = 16
_PADDING_TOP = 28
_PADDING_BOTTOM = 32

_PLOT_LEFT = _PADDING_LEFT
_PLOT_RIGHT = WIDTH - _PADDING_RIGHT
_PLOT_TOP = _PADDING_TOP
_PLOT_BOTTOM = HEIGHT - _PADDING_BOTTOM
_PLOT_WIDTH = _PLOT_RIGHT - _PLOT_LEFT
_PLOT_HEIGHT = _PLOT_BOTTOM - _PLOT_TOP

_BAR_MAX_WIDTH = 24
_BAR_CORNER_RADIUS = 4


def _format_value(value: int) -> str:
    return f"{value:,}"


def _nice_step(raw_step: float) -> float:
    if raw_step <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw_step))
    residual = raw_step / magnitude
    if residual <= 1:
        nice = 1
    elif residual <= 2:
        nice = 2
    elif residual <= 5:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def _tick_values(max_value: int, count: int = 4) -> list[int]:
    if max_value <= 0:
        return [0]
    step = _nice_step(max_value / count)
    ticks = [0.0]
    while ticks[-1] < max_value:
        ticks.append(ticks[-1] + step)
    return [int(tick) for tick in ticks]


def _axis_and_gridlines(max_value: int) -> tuple[list[int], str]:
    ticks = _tick_values(max_value)
    axis_max = max(ticks[-1], 1)
    elements = []
    for tick in ticks:
        y = _PLOT_BOTTOM - (_PLOT_HEIGHT * tick / axis_max)
        elements.append(
            f'<line x1="{_PLOT_LEFT:.2f}" y1="{y:.2f}" x2="{_PLOT_RIGHT:.2f}" y2="{y:.2f}" '
            f'stroke="{GRIDLINE}" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{_PLOT_LEFT - 8:.2f}" y="{y + 4:.2f}" text-anchor="end" '
            f'font-size="11" fill="{MUTED_INK}">{_format_value(tick)}</text>'
        )
    return ticks, "\n  ".join(elements)


def _svg_wrapper(title: str, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{title}">\n'
        f'  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{SURFACE}"/>\n'
        f'  <text x="{_PADDING_LEFT}" y="18" font-size="13" font-weight="600" '
        f'fill="{PRIMARY_INK}">{title}</text>\n'
        f"  {body}\n"
        f"</svg>\n"
    )


def render_line_chart(*, title: str, series: list[tuple[str, int | None]]) -> str:
    """Render a deterministic single-series line chart as an SVG string.

    ``series`` is ``(label, value)`` in chronological order; ``value`` may
    be ``None`` for a point with no data, which breaks the line rather
    than being plotted as zero.
    """
    known_values = [value for _, value in series if value is not None]
    max_value = max(known_values) if known_values else 0
    ticks, grid_and_labels = _axis_and_gridlines(max_value)
    axis_max = max(ticks[-1], 1)

    def x_for(index: int) -> float:
        if len(series) <= 1:
            return _PLOT_LEFT + _PLOT_WIDTH / 2
        return _PLOT_LEFT + (_PLOT_WIDTH * index / (len(series) - 1))

    def y_for(value: int) -> float:
        return _PLOT_BOTTOM - (_PLOT_HEIGHT * value / axis_max)

    segments: list[list[tuple[float, float]]] = []
    for index, (_, value) in enumerate(series):
        if value is None:
            continue
        point = (x_for(index), y_for(value))
        if segments and index > 0 and series[index - 1][1] is not None:
            segments[-1].append(point)
        else:
            segments.append([point])

    path_elements = []
    for segment in segments:
        if len(segment) < 2:
            continue
        path_d = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in segment)
        path_elements.append(
            f'<path d="{path_d}" fill="none" stroke="{SERIES_BLUE}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )

    end_marker = ""
    last_index = next(
        (i for i in range(len(series) - 1, -1, -1) if series[i][1] is not None), None
    )
    if last_index is not None:
        last_x, last_y = x_for(last_index), y_for(series[last_index][1])
        label_above = last_y - 10 > _PLOT_TOP + 8
        label_y = last_y - 10 if label_above else last_y + 18
        end_marker = (
            f'<circle cx="{last_x:.2f}" cy="{last_y:.2f}" r="4" fill="{SERIES_BLUE}" '
            f'stroke="{SURFACE}" stroke-width="2"/>\n'
            f'  <text x="{last_x:.2f}" y="{label_y:.2f}" text-anchor="end" font-size="11" '
            f'font-weight="600" fill="{PRIMARY_INK}">{_format_value(series[last_index][1])}</text>'
        )

    baseline = (
        f'<line x1="{_PLOT_LEFT:.2f}" y1="{_PLOT_BOTTOM:.2f}" x2="{_PLOT_RIGHT:.2f}" '
        f'y2="{_PLOT_BOTTOM:.2f}" stroke="{BASELINE}" stroke-width="1"/>'
    )

    body = "\n  ".join([grid_and_labels, baseline, *path_elements, end_marker])
    return _svg_wrapper(title, body)


def render_bar_chart(*, title: str, series: list[tuple[str, int | None]]) -> str:
    """Render a deterministic single-series bar chart as an SVG string.

    ``series`` is ``(label, value)`` in chronological order; ``value`` may
    be ``None`` for a position with no data, which is simply skipped
    rather than drawn as a zero-height bar.
    """
    known_values = [value for _, value in series if value is not None]
    max_value = max(known_values) if known_values else 0
    ticks, grid_and_labels = _axis_and_gridlines(max_value)
    axis_max = max(ticks[-1], 1)

    band_width = _PLOT_WIDTH / len(series) if series else _PLOT_WIDTH
    bar_width = min(_BAR_MAX_WIDTH, max(2.0, band_width - 4))

    bar_elements = []
    last_index = next(
        (i for i in range(len(series) - 1, -1, -1) if series[i][1] is not None), None
    )
    for index, (_, value) in enumerate(series):
        if value is None:
            continue
        band_center = _PLOT_LEFT + band_width * (index + 0.5)
        bar_x = band_center - bar_width / 2
        bar_height = _PLOT_HEIGHT * value / axis_max
        bar_y = _PLOT_BOTTOM - bar_height
        radius = min(_BAR_CORNER_RADIUS, bar_width / 2, bar_height)
        if bar_height <= 0:
            path_d = f"M {bar_x:.2f},{_PLOT_BOTTOM:.2f} L {bar_x + bar_width:.2f},{_PLOT_BOTTOM:.2f}"
        else:
            path_d = (
                f"M {bar_x:.2f},{_PLOT_BOTTOM:.2f} "
                f"L {bar_x:.2f},{bar_y + radius:.2f} "
                f"Q {bar_x:.2f},{bar_y:.2f} {bar_x + radius:.2f},{bar_y:.2f} "
                f"L {bar_x + bar_width - radius:.2f},{bar_y:.2f} "
                f"Q {bar_x + bar_width:.2f},{bar_y:.2f} {bar_x + bar_width:.2f},{bar_y + radius:.2f} "
                f"L {bar_x + bar_width:.2f},{_PLOT_BOTTOM:.2f} "
                f"Z"
            )
        bar_elements.append(f'<path d="{path_d}" fill="{SERIES_BLUE}"/>')

        if index == last_index:
            label_y = max(bar_y - 6, _PLOT_TOP + 10)
            bar_elements.append(
                f'<text x="{band_center:.2f}" y="{label_y:.2f}" text-anchor="middle" '
                f'font-size="11" font-weight="600" fill="{PRIMARY_INK}">'
                f"{_format_value(value)}</text>"
            )

    baseline = (
        f'<line x1="{_PLOT_LEFT:.2f}" y1="{_PLOT_BOTTOM:.2f}" x2="{_PLOT_RIGHT:.2f}" '
        f'y2="{_PLOT_BOTTOM:.2f}" stroke="{BASELINE}" stroke-width="1"/>'
    )

    body = "\n  ".join([grid_and_labels, baseline, *bar_elements])
    return _svg_wrapper(title, body)
