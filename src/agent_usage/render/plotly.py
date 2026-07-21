"""Deterministic Plotly PNG charts for the profile README dashboard.

GitHub README files cannot execute Plotly JavaScript, so charts are rendered
through Plotly and Kaleido into static PNG assets. PNG avoids SVG proxying and
sanitization differences across GitHub and Markdown preview clients while
preserving Plotly's layout, typography, legends, and stacked-series semantics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import plotly.graph_objects as go
import plotly.io as pio

CHART_WIDTH = 960
_TOKEN_CHART_HEIGHT = 300

_BACKGROUND = "#ffffff"
_GRID = "#e5e7eb"
_AXIS = "#6b7280"
_TEXT = "#111827"
_INPUT = "#2563eb"
_OUTPUT = "#14b8a6"
_REASONING = "#a855f7"

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

_AGENT_BAR_HEIGHT = 150
_AGENT_BAR_MARGIN = {"l": 12, "r": 24, "t": 48, "b": 12}
_AGENT_SERIES = (
    ("hermes_agent", "Hermes", "#f59e0b"),
    ("claude_code", "Claude Code", "#d97757"),
    ("codex", "Codex", "#10a37f"),
)


TokenPoint = tuple[str, dict[str, int] | None]


def rank_usage(counters: Mapping[str, int]) -> list[tuple[str, int]]:
    """Return usage counters in the display order used by horizontal charts."""
    return sorted(counters.items(), key=lambda item: (-item[1], item[0]))


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


def _to_static_png(figure: go.Figure) -> bytes:
    """Export a high-resolution PNG that can be embedded in a README reliably."""
    return pio.to_image(
        figure,
        format="png",
        width=figure.layout.width,
        height=figure.layout.height,
        scale=2,
    )


def render_stacked_token_chart(*, title: str, series: Sequence[TokenPoint]) -> bytes:
    """Render daily input/output/reasoning use as a static stacked Plotly PNG."""
    x_values = [day for day, _ in series]
    figure = go.Figure()
    for key, label, color in (
        ("input", "Input", _INPUT),
        ("output", "Output", _OUTPUT),
        ("reasoning", "Reasoning", _REASONING),
    ):
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=[point[key] if point is not None else None for _, point in series],
                mode="lines",
                name=label,
                stackgroup="tokens",
                line={"color": color, "width": 2},
                fillcolor=color,
                opacity=0.82,
                connectgaps=False,
                hovertemplate=f"%{{x}}<br>{label}: %{{y:,}} tokens<extra></extra>",
            )
        )

    figure.update_layout(
        **_base_layout(title=title, height=_TOKEN_CHART_HEIGHT),
        hovermode="x unified",
        legend={
            "orientation": "h",
            "traceorder": "normal",
            "x": 0,
            "y": 1.15,
            "xanchor": "left",
        },
    )
    figure.update_xaxes(
        type="date",
        showgrid=False,
        tickformat="%b %d",
        tickangle=-35,
        linecolor=_AXIS,
        tickfont={"color": _AXIS},
        fixedrange=True,
    )
    figure.update_yaxes(
        title_text="Tokens",
        separatethousands=True,
        gridcolor=_GRID,
        zerolinecolor=_GRID,
        linecolor=_AXIS,
        tickfont={"color": _AXIS},
        fixedrange=True,
    )
    return _to_static_png(figure)


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
