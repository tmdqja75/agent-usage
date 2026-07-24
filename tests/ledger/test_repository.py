"""Tests for the private local usage ledger repository."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_usage.ledger.repository import LedgerRepository
from agent_usage.models import NormalizedUsageRecord, SourceStatus, SupportedAgent, TokenUsage


UTC = timezone.utc


@pytest.fixture
def repository(tmp_path):
    repo = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    yield repo
    repo.close()


def _record(
    fingerprint: str,
    *,
    agent: SupportedAgent = SupportedAgent.CLAUDE_CODE,
    occurred_at: datetime = datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    session_fingerprint: str | None = None,
    tokens: TokenUsage | None = TokenUsage(input_tokens=10, output_tokens=5, reasoning_tokens=1),
    source_status: SourceStatus = SourceStatus.AVAILABLE_WITH_ACTIVITY,
    observed_skill_name: str | None = None,
    observed_mcp_server_name: str | None = None,
    observed_mcp_tool_name: str | None = None,
) -> NormalizedUsageRecord:
    return NormalizedUsageRecord(
        agent=agent,
        occurred_at=occurred_at,
        fingerprint=fingerprint,
        session_fingerprint=session_fingerprint,
        tokens=tokens,
        observed_skill_name=observed_skill_name,
        observed_mcp_server_name=observed_mcp_server_name,
        observed_mcp_tool_name=observed_mcp_tool_name,
        source_status=source_status,
    )


def test_open_creates_missing_parent_directories(tmp_path) -> None:
    nested_path = tmp_path / "nested" / "subdir" / "ledger.sqlite3"

    repo = LedgerRepository.open(nested_path)
    try:
        assert nested_path.exists()
    finally:
        repo.close()


def test_schema_creates_expected_ledger_tables(tmp_path) -> None:
    repo = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        table_names = {
            row[0]
            for row in repo._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "events",
            "checkpoints",
            "daily_aggregates",
            "device_identity",
            "schema_migrations",
        } <= table_names
    finally:
        repo.close()


def test_insert_and_list_round_trips_a_normalized_record(repository) -> None:
    record = _record(
        "fingerprint-one",
        session_fingerprint="opaque-session-hash",
        observed_skill_name="safe-skill",
        observed_mcp_server_name="local-server",
        observed_mcp_tool_name="safe-tool",
    )

    inserted = repository.insert_records([record])

    assert inserted == 1
    stored = repository.list_records()
    assert stored == [record]
    assert stored[0].session_fingerprint == "opaque-session-hash"


def test_session_fingerprint_round_trips_as_none_when_unset(repository) -> None:
    record = _record("fingerprint-no-session")

    repository.insert_records([record])

    [stored] = repository.list_records()
    assert stored.session_fingerprint is None


def test_insert_preserves_source_unavailable_with_none_tokens(repository) -> None:
    record = _record(
        "fingerprint-unavailable",
        tokens=None,
        source_status=SourceStatus.SOURCE_UNAVAILABLE,
    )

    repository.insert_records([record])

    [stored] = repository.list_records()
    assert stored.source_status is SourceStatus.SOURCE_UNAVAILABLE
    assert stored.tokens is None


def test_insert_preserves_zero_activity_tokens(repository) -> None:
    record = _record(
        "fingerprint-zero",
        tokens=TokenUsage(),
        source_status=SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY,
    )

    repository.insert_records([record])

    [stored] = repository.list_records()
    assert stored.source_status is SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY
    assert stored.headline_total == 0


def test_duplicate_fingerprint_is_rejected_on_repeat_import(repository) -> None:
    record = _record("duplicate-fingerprint")

    first_pass = repository.insert_records([record])
    second_pass = repository.insert_records([record])

    assert first_pass == 1
    assert second_pass == 0
    assert len(repository.list_records()) == 1


def test_repeat_import_leaves_totals_unchanged(repository) -> None:
    records = [
        _record("fp-1", tokens=TokenUsage(input_tokens=10, output_tokens=5, reasoning_tokens=0)),
        _record("fp-2", tokens=TokenUsage(input_tokens=3, output_tokens=2, reasoning_tokens=1)),
    ]

    repository.insert_records(records)
    totals_after_first_import = sum(r.headline_total for r in repository.list_records())

    repository.insert_records(records)
    totals_after_repeat_import = sum(r.headline_total for r in repository.list_records())

    assert totals_after_first_import == 21
    assert totals_after_repeat_import == totals_after_first_import


def test_list_records_can_filter_by_agent(repository) -> None:
    repository.insert_records(
        [
            _record("fp-claude", agent=SupportedAgent.CLAUDE_CODE),
            _record("fp-codex", agent=SupportedAgent.CODEX),
        ]
    )

    claude_only = repository.list_records(agent=SupportedAgent.CLAUDE_CODE)

    assert [r.fingerprint for r in claude_only] == ["fp-claude"]


def test_checkpoint_round_trips_and_defaults_to_none(repository) -> None:
    assert repository.get_checkpoint(SupportedAgent.CODEX) is None

    repository.set_checkpoint(
        SupportedAgent.CODEX, datetime(2026, 7, 10, 8, 30, tzinfo=UTC)
    )

    assert repository.get_checkpoint(SupportedAgent.CODEX) == datetime(
        2026, 7, 10, 8, 30, tzinfo=UTC
    )


def test_checkpoint_update_overwrites_previous_value(repository) -> None:
    repository.set_checkpoint(
        SupportedAgent.HERMES_AGENT, datetime(2026, 7, 5, tzinfo=UTC)
    )
    repository.set_checkpoint(
        SupportedAgent.HERMES_AGENT, datetime(2026, 7, 12, tzinfo=UTC)
    )

    assert repository.get_checkpoint(SupportedAgent.HERMES_AGENT) == datetime(
        2026, 7, 12, tzinfo=UTC
    )


def test_checkpoint_is_independent_per_agent(repository) -> None:
    repository.set_checkpoint(
        SupportedAgent.CODEX, datetime(2026, 7, 6, tzinfo=UTC)
    )

    assert repository.get_checkpoint(SupportedAgent.HERMES_AGENT) is None


def test_get_earliest_record_at_returns_none_when_agent_has_no_records(tmp_path) -> None:
    repo = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        assert repo.get_earliest_record_at(SupportedAgent.CLAUDE_CODE) is None
    finally:
        repo.close()


def test_get_earliest_record_at_returns_the_minimum_occurred_at_for_that_agent(tmp_path) -> None:
    repo = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        repo.insert_records(
            [
                _record("a", occurred_at=datetime(2026, 7, 10, tzinfo=UTC)),
                _record("b", occurred_at=datetime(2026, 7, 5, tzinfo=UTC)),
                _record("c", occurred_at=datetime(2026, 7, 20, tzinfo=UTC)),
                _record(
                    "d",
                    agent=SupportedAgent.CODEX,
                    occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
                ),
            ]
        )
        earliest = repo.get_earliest_record_at(SupportedAgent.CLAUDE_CODE)
    finally:
        repo.close()

    assert earliest == datetime(2026, 7, 5, tzinfo=UTC)
