"""Tests for README dashboard Markdown rendering and marker splicing."""

from __future__ import annotations

from datetime import date, datetime, timezone

from agent_usage.models import NormalizedUsageRecord, SourceStatus, SupportedAgent, TokenUsage
from agent_usage.public_data import build_daily_record
from agent_usage.render.markdown import (
    MARKER_END,
    MARKER_START,
    render_dashboard,
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


def test_render_dashboard_produces_only_the_requested_readme_sections_and_plotly_svgs() -> None:
    payloads = [_payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.CLAUDE_CODE)]

    result = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")

    assert result["markdown"].startswith(MARKER_START)
    assert result["markdown"].endswith(MARKER_END)
    assert result["markdown"].count(MARKER_START) == 1
    assert result["markdown"].count(MARKER_END) == 1
    assert "## Token Usage" in result["markdown"]
    assert "### Rolling 14 Days Activity" in result["markdown"]
    assert "## Total Activity" in result["markdown"]
    assert "## Skill/MCP Usage" in result["markdown"]
    assert "### Skills" in result["markdown"]
    assert "### MCP" in result["markdown"]
    assert "Source Health" not in result["markdown"]
    assert "Last updated" not in result["markdown"]
    assert "|" not in result["markdown"]
    for asset in result["charts"].values():
        assert asset.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_dashboard_is_deterministic_regardless_of_payload_order() -> None:
    payloads = [
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.CLAUDE_CODE),
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ACTIVITY, SupportedAgent.HERMES_AGENT),
        _payload_with_status(SourceStatus.SOURCE_UNAVAILABLE, SupportedAgent.CODEX),
    ]

    first = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")
    second = render_dashboard(list(reversed(payloads)), today=TODAY, generated_at="2026-07-18")

    assert first == second


def test_render_dashboard_keeps_source_status_out_of_the_readme() -> None:
    payloads = [
        _payload_with_status(SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY, SupportedAgent.HERMES_AGENT),
        _payload_with_status(SourceStatus.SOURCE_UNAVAILABLE, SupportedAgent.CODEX),
    ]

    result = render_dashboard(payloads, today=TODAY, generated_at="2026-07-18")

    assert "Zero activity" not in result["markdown"]
    assert "Unavailable" not in result["markdown"]


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
