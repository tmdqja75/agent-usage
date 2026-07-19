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
_TOKEN_CHART_HEIGHT = 390
_MIN_USAGE_CHART_HEIGHT = 260
_USAGE_ROW_HEIGHT = 34

_BACKGROUND = "#ffffff"
_GRID = "#e5e7eb"
_AXIS = "#6b7280"
_TEXT = "#111827"
_INPUT = "#2563eb"
_OUTPUT = "#14b8a6"
_REASONING = "#a855f7"
_USAGE = "#2563eb"



TokenPoint = tuple[str, dict[str, int] | None]


def rank_usage(counters: Mapping[str, int]) -> list[tuple[str, int]]:
    """Return usage counters in the display order used by horizontal charts."""
    return sorted(counters.items(), key=lambda item: (-item[1], item[0]))


def _base_layout(*, title: str, height: int) -> dict:
    return {
        "width": CHART_WIDTH,
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
        width=CHART_WIDTH,
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


def render_usage_bar_chart(*, title: str, counters: Mapping[str, int]) -> bytes:
    """Render all observed Skill or MCP counts as a ranked horizontal bar chart."""
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
        figure.update_layout(**_base_layout(title=title, height=_MIN_USAGE_CHART_HEIGHT))
        figure.update_xaxes(visible=False, fixedrange=True)
        figure.update_yaxes(visible=False, fixedrange=True)
        return _to_static_png(figure)

    names, counts = zip(*ranked, strict=True)
    height = max(_MIN_USAGE_CHART_HEIGHT, len(ranked) * _USAGE_ROW_HEIGHT + 110)
    figure = go.Figure(
        go.Bar(
            x=counts,
            y=names,
            orientation="h",
            marker={"color": _USAGE},
            text=[f"{count:,}" for count in counts],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:,} calls<extra></extra>",
        )
    )
    figure.update_layout(**_base_layout(title=title, height=height), showlegend=False)
    figure.update_xaxes(
        title_text="Calls",
        separatethousands=True,
        gridcolor=_GRID,
        zerolinecolor=_GRID,
        linecolor=_AXIS,
        tickfont={"color": _AXIS},
        fixedrange=True,
    )
    figure.update_yaxes(
        categoryorder="array",
        categoryarray=list(reversed(names)),
        automargin=True,
        tickfont={"color": _TEXT},
        fixedrange=True,
    )
    return _to_static_png(figure)
