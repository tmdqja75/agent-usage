"""Tests for pulling local agent usage into the private ledger."""

from __future__ import annotations

from datetime import datetime, timezone

from codex_sessions import token_count_event, write_rollout

from agent_usage.commands.collect import (
    AgentCollectionResult,
    collect_agent,
    collect_all,
    collection_window,
    overall_source_status,
)
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.models import NormalizedUsageRecord, SourceStatus, SupportedAgent, TokenUsage
from agent_usage.time_window import INITIAL_COLLECTION_WINDOW

UTC = timezone.utc
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _source_paths(tmp_path, **overrides):
    paths = {
        "hermes_db": tmp_path / "missing-hermes.db",
        "claude_projects_dir": tmp_path / "missing-claude",
        "codex_sessions_dir": tmp_path / "missing-codex",
    }
    paths.update(overrides)
    return paths


def _write_codex_activity(tmp_path, *, timestamp="2026-07-10T10:00:00+00:00"):
    sessions_dir = tmp_path / "codex_sessions"
    write_rollout(
        sessions_dir / "session-a" / "rollout-1.jsonl",
        "session-a",
        [token_count_event(timestamp, total_input=100, total_output=50, total_reasoning=0)],
    )
    return sessions_dir


# --- collection_window -------------------------------------------------


def test_collection_window_uses_the_initial_backfill_when_no_checkpoint(tmp_path) -> None:
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        window = collection_window(SupportedAgent.CLAUDE_CODE, repository, now=NOW)
    finally:
        repository.close()

    assert window is not None
    assert window.start_utc == INITIAL_COLLECTION_WINDOW.start_utc
    assert window.end_utc == NOW


def test_collection_window_never_extends_the_initial_backfill_past_its_own_end(tmp_path) -> None:
    far_future = datetime(2027, 1, 1, tzinfo=UTC)
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        window = collection_window(SupportedAgent.CLAUDE_CODE, repository, now=far_future)
    finally:
        repository.close()

    assert window is not None
    assert window.start_utc == INITIAL_COLLECTION_WINDOW.start_utc
    assert window.end_utc == INITIAL_COLLECTION_WINDOW.end_utc


def test_collection_window_continues_from_the_checkpoint_after_the_first_run(tmp_path) -> None:
    checkpoint = datetime(2026, 7, 18, tzinfo=UTC)
    later = datetime(2026, 7, 20, tzinfo=UTC)
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        repository.set_checkpoint(SupportedAgent.CLAUDE_CODE, checkpoint)
        window = collection_window(SupportedAgent.CLAUDE_CODE, repository, now=later)
    finally:
        repository.close()

    assert window is not None
    assert window.start_utc == checkpoint
    assert window.end_utc == later


def test_collection_window_is_none_when_already_caught_up(tmp_path) -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        repository.set_checkpoint(SupportedAgent.CLAUDE_CODE, now)
        window = collection_window(SupportedAgent.CLAUDE_CODE, repository, now=now)
    finally:
        repository.close()

    assert window is None


# --- overall_source_status ----------------------------------------------


def test_overall_source_status_prefers_activity_over_zero_and_unavailable() -> None:
    unavailable = NormalizedUsageRecord(
        agent=SupportedAgent.CLAUDE_CODE,
        occurred_at=NOW,
        fingerprint="a",
        tokens=None,
        source_status=SourceStatus.SOURCE_UNAVAILABLE,
    )
    zero = NormalizedUsageRecord(
        agent=SupportedAgent.CLAUDE_CODE,
        occurred_at=NOW,
        fingerprint="b",
        tokens=TokenUsage(),
        source_status=SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY,
    )
    active = NormalizedUsageRecord(
        agent=SupportedAgent.CLAUDE_CODE,
        occurred_at=NOW,
        fingerprint="c",
        tokens=TokenUsage(input_tokens=1),
        source_status=SourceStatus.AVAILABLE_WITH_ACTIVITY,
    )

    assert overall_source_status([unavailable, zero, active]) is SourceStatus.AVAILABLE_WITH_ACTIVITY
    assert overall_source_status([unavailable, zero]) is SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY
    assert overall_source_status([unavailable]) is SourceStatus.SOURCE_UNAVAILABLE
    assert overall_source_status([]) is SourceStatus.SOURCE_UNAVAILABLE


# --- collect_all: unavailable / zero / active differ ---------------------


def test_collect_all_distinguishes_unavailable_zero_and_active_sources(tmp_path) -> None:
    claude_projects_dir = tmp_path / "claude_projects"
    claude_projects_dir.mkdir()
    codex_sessions_dir = _write_codex_activity(tmp_path)

    results = collect_all(
        ledger_path=tmp_path / "ledger.sqlite3",
        hermes_db=tmp_path / "missing-hermes.db",
        claude_projects_dir=claude_projects_dir,
        codex_sessions_dir=codex_sessions_dir,
        now=NOW,
    )

    by_agent = {result.agent: result for result in results}
    assert by_agent[SupportedAgent.HERMES_AGENT].status is SourceStatus.SOURCE_UNAVAILABLE
    assert by_agent[SupportedAgent.CLAUDE_CODE].status is SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY
    assert by_agent[SupportedAgent.CODEX].status is SourceStatus.AVAILABLE_WITH_ACTIVITY


# --- dry-run has no side effects -----------------------------------------


def test_collect_all_dry_run_does_not_write_to_the_ledger_or_move_checkpoints(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    codex_sessions_dir = _write_codex_activity(tmp_path)

    results = collect_all(
        ledger_path=ledger_path,
        **_source_paths(tmp_path, codex_sessions_dir=codex_sessions_dir),
        now=NOW,
        dry_run=True,
    )

    codex_result = next(r for r in results if r.agent is SupportedAgent.CODEX)
    assert codex_result.status is SourceStatus.AVAILABLE_WITH_ACTIVITY
    assert codex_result.records_observed > 0
    assert codex_result.records_inserted == 0

    repository = LedgerRepository.open(ledger_path)
    try:
        assert repository.list_records() == []
        assert repository.get_checkpoint(SupportedAgent.CODEX) is None
    finally:
        repository.close()


def test_collect_all_real_run_persists_records_and_advances_checkpoints(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    codex_sessions_dir = _write_codex_activity(tmp_path)

    collect_all(
        ledger_path=ledger_path,
        **_source_paths(tmp_path, codex_sessions_dir=codex_sessions_dir),
        now=NOW,
        dry_run=False,
    )

    repository = LedgerRepository.open(ledger_path)
    try:
        records = repository.list_records(SupportedAgent.CODEX)
        checkpoint = repository.get_checkpoint(SupportedAgent.CODEX)
    finally:
        repository.close()

    assert len(records) == 1
    assert checkpoint == NOW


def test_collect_all_repeat_runs_with_the_same_now_do_not_double_count(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    codex_sessions_dir = _write_codex_activity(tmp_path)
    kwargs = dict(
        ledger_path=ledger_path,
        **_source_paths(tmp_path, codex_sessions_dir=codex_sessions_dir),
        now=NOW,
    )

    first = collect_all(**kwargs)
    second = collect_all(**kwargs)

    codex_first = next(r for r in first if r.agent is SupportedAgent.CODEX)
    codex_second = next(r for r in second if r.agent is SupportedAgent.CODEX)
    assert codex_first.records_inserted == 1
    assert codex_second.status is None

    repository = LedgerRepository.open(ledger_path)
    try:
        records = repository.list_records(SupportedAgent.CODEX)
    finally:
        repository.close()
    assert len(records) == 1


# --- collect_agent / AgentCollectionResult --------------------------------


def test_collect_agent_reports_none_status_when_nothing_new(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    repository = LedgerRepository.open(ledger_path)
    try:
        repository.set_checkpoint(SupportedAgent.CODEX, NOW)
        result = collect_agent(
            SupportedAgent.CODEX,
            lambda path, window: [],
            tmp_path / "unused",
            repository,
            now=NOW,
            dry_run=False,
        )
    finally:
        repository.close()

    assert result == AgentCollectionResult(
        agent=SupportedAgent.CODEX, status=None, records_observed=0, records_inserted=0
    )
