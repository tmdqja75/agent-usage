from datetime import date

from agent_usage.render.dashboard_data import build_dashboard_data

_STATUS = "available_with_activity"


def _agent(input_=0, output=0, reasoning=0, headline=0, sessions=0, status=_STATUS):
    return {
        "input_tokens": input_,
        "output_tokens": output,
        "reasoning_tokens": reasoning,
        "headline_total": headline,
        "session_count": sessions,
        "source_status": status,
    }


def _payload(day, *, device="dev1", claude=None, codex=None, skills=None, mcp=None):
    return {
        "schema_version": 1,
        "device_id": device,
        "date": day,
        "agents": {
            "claude_code": claude or _agent(status="source_unavailable"),
            "codex": codex or _agent(status="source_unavailable"),
            "hermes_agent": _agent(status="source_unavailable"),
        },
        "skills": skills or {},
        "mcp_servers": mcp or {},
        "mcp_tools": {},
    }


def test_build_dashboard_data_shapes_every_section():
    payloads = [
        _payload(
            "2026-07-10",
            claude=_agent(input_=100, output=50, reasoning=0, headline=150),
            skills={"brainstorming": 3, "tdd": 2, "graphify": 1},
            mcp={"gmail": 4, "calendar": 1},
        ),
        _payload(
            "2026-07-11",
            codex=_agent(input_=10, output=5, reasoning=2, headline=17),
        ),
    ]

    data = build_dashboard_data(payloads, today=date(2026, 7, 11), window_days=14, pie_top_n=2)

    assert data["window"] == {"start": "2026-07-10", "end": "2026-07-11"}
    assert data["tokens"] == [
        {"date": "2026-07-10", "input": 100, "output": 50, "reasoning": 0},
        {"date": "2026-07-11", "input": 10, "output": 5, "reasoning": 2},
    ]
    assert {"agent": "claude_code", "tokens": 150} in data["agents"]
    assert {"agent": "codex", "tokens": 17} in data["agents"]
    # pie_top_n=2 keeps top 2 skills and folds the rest into "Other"
    assert data["skills"] == [
        {"name": "brainstorming", "count": 3},
        {"name": "tdd", "count": 2},
        {"name": "Other", "count": 1},
    ]
    assert data["mcp"] == [{"name": "gmail", "count": 4}, {"name": "calendar", "count": 1}]
    assert data["heatmap"] == [
        {"date": "2026-07-10", "tokens": 150},
        {"date": "2026-07-11", "tokens": 17},
    ]


def test_build_dashboard_data_empty_uses_window_fallback():
    data = build_dashboard_data([], today=date(2026, 7, 18), window_days=14)
    assert data["window"] == {"start": "2026-07-05", "end": "2026-07-18"}
    assert data["tokens"] == []
    assert data["skills"] == []
    assert data["mcp"] == []
    assert data["heatmap"] == []
    assert all(entry["tokens"] == 0 for entry in data["agents"])
