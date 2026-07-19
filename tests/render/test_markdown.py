"""Tests for README dashboard Markdown rendering and marker splicing."""

from __future__ import annotations

from datetime import date, datetime, timezone

from agent_usage.models import NormalizedUsageRecord, SourceStatus, SupportedAgent, TokenUsage
from agent_usage.public_data import build_daily_record
from agent_usage.render.markdown import (
    MARKER_END,
    MARKER_START,
    render_dashboard,
    render_leaderboard_table,
    render_source_health_table,
    update_readme,
)

UTC = timezone.utc
TODAY = date(2026, 7, 18)


def _payload_with_status(status: SourceStatus, agent: SupportedAgent) -> dict:
    if status is SourceStatus.SOURCE_UNAVAILABLE:
        tokens = None
    elif status is SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY:
        tokens = TokenUsage()
    else:
        tokens = TokenUsage(input_tokens=5)

    record = NormalizedUsageRecord(
        agent=agent,
        occurred_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
        fingerprint=f"fp-{agent.value}",
        session_fingerprint=f"s-{agent.value}",
        tokens=tokens,
        source_status=status,
    )
    return build_daily_record(device_id="device-a", day=date(2026, 7, 10), records=[record])


def test_render_source_health_table_shows_all_three_states() -> None:
    payloads = [
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.HERMES_AGENT),
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY, SupportedAgent.CLAUDE_CODE),
        _payload_with_status(SourceStatus.SOURCE_UNAVAILABLE, SupportedAgent.CODEX),
    ]
    from agent_usage.aggregate import aggregate_records

    summary = aggregate_records(payloads)
    table = render_source_health_table(summary)

    assert "Hermes Agent" in table
    assert "Claude Code" in table
    assert "Codex" in table
    assert "Active" in table
    assert "Zero activity" in table
    assert "Unavailable" in table


def test_render_leaderboard_table_shows_placeholder_when_empty() -> None:
    table = render_leaderboard_table({}, header="Skill")

    assert "no" in table.lower() or "none" in table.lower()


def test_render_leaderboard_table_caps_at_top_n_and_orders_by_count() -> None:
    counters = {f"skill-{i}": i for i in range(20)}

    table = render_leaderboard_table(counters, header="Skill", top_n=5)

    assert table.count("| skill-") == 5
    assert "skill-19" in table
    assert "skill-0 " not in table


def test_render_dashboard_produces_bounded_markers_and_valid_svgs() -> None:
    payloads = [_payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.CLAUDE_CODE)]

    result = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")

    assert result["markdown"].startswith(MARKER_START)
    assert result["markdown"].endswith(MARKER_END)
    assert result["markdown"].count(MARKER_START) == 1
    assert result["markdown"].count(MARKER_END) == 1
    assert "<svg" in result["rolling_svg"]
    assert "<svg" in result["lifetime_svg"]


def test_render_dashboard_is_deterministic_regardless_of_payload_order() -> None:
    payloads = [
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.CLAUDE_CODE),
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.HERMES_AGENT),
        _payload_with_status(SourceStatus.SOURCE_UNAVAILABLE, SupportedAgent.CODEX),
    ]

    first = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")
    second = render_dashboard(list(reversed(payloads)), today=TODAY, generated_at="2026-07-18")

    assert first == second


def test_render_dashboard_markdown_reflects_zero_and_unavailable_states() -> None:
    payloads = [
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY, SupportedAgent.HERMES_AGENT),
        _payload_with_status(SourceStatus.SOURCE_UNAVAILABLE, SupportedAgent.CODEX),
    ]

    result = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")

    assert "Zero activity" in result["markdown"]
    assert "Unavailable" in result["markdown"]


def test_update_readme_preserves_content_outside_markers() -> None:
    existing = "# My Profile\n\nSome intro text.\n\n## Other Section\nMore content.\n"
    dashboard = f"{MARKER_START}\nDASHBOARD CONTENT\n{MARKER_END}"

    updated = update_readme(existing, dashboard)

    assert "# My Profile" in updated
    assert "Some intro text." in updated
    assert "## Other Section" in updated
    assert "DASHBOARD CONTENT" in updated


def test_update_readme_replaces_existing_managed_section_without_duplicating() -> None:
    existing = f"# My Profile\n\n{MARKER_START}\nOLD CONTENT\n{MARKER_END}\n\nFooter text.\n"
    dashboard = f"{MARKER_START}\nNEW CONTENT\n{MARKER_END}"

    updated = update_readme(existing, dashboard)

    assert "OLD CONTENT" not in updated
    assert "NEW CONTENT" in updated
    assert updated.count(MARKER_START) == 1
    assert updated.count(MARKER_END) == 1
    assert "Footer text." in updated


def test_update_readme_appends_markers_when_none_exist() -> None:
    existing = "# My Profile\n\nJust some text, no markers yet.\n"
    dashboard = f"{MARKER_START}\nDASHBOARD CONTENT\n{MARKER_END}"

    updated = update_readme(existing, dashboard)

    assert "# My Profile" in updated
    assert "Just some text, no markers yet." in updated
    assert "DASHBOARD CONTENT" in updated
    assert updated.count(MARKER_START) == 1


def test_update_readme_is_idempotent() -> None:
    existing = "# My Profile\n\nIntro.\n"
    dashboard = f"{MARKER_START}\nDASHBOARD CONTENT\n{MARKER_END}"

    once = update_readme(existing, dashboard)
    twice = update_readme(once, dashboard)

    assert once == twice


def test_update_readme_handles_an_empty_existing_readme() -> None:
    dashboard = f"{MARKER_START}\nDASHBOARD CONTENT\n{MARKER_END}"

    updated = update_readme("", dashboard)

    assert updated.strip() == dashboard.strip()


def test_generated_tables_are_valid_markdown_pipe_tables() -> None:
    import re

    payloads = [_payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.CLAUDE_CODE)]
    result = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")

    row_pattern = re.compile(r"^\|.+\|$")
    separator_pattern = re.compile(r"^\|(\s*:?-+:?\s*\|)+$")

    lines = result["markdown"].splitlines()
    table_blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("|"):
            current.append(line)
        elif current:
            table_blocks.append(current)
            current = []
    if current:
        table_blocks.append(current)

    assert table_blocks, "expected at least one Markdown table in the rendered dashboard"

    for block in table_blocks:
        assert len(block) >= 2, f"table block has no separator row: {block!r}"
        assert row_pattern.match(block[0]), f"header row is not a valid pipe row: {block[0]!r}"
        assert separator_pattern.match(block[1]), f"second row is not a valid separator: {block[1]!r}"
        for row in block[2:]:
            assert row_pattern.match(row), f"data row is not a valid pipe row: {row!r}"
