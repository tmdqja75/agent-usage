"""Tests for local, read-only diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone

from codex_sessions import token_count_event, write_rollout

from agent_usage.commands.doctor import run_doctor
from agent_usage.config import AppConfig, save_config
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.models import SourceStatus, SupportedAgent

UTC = timezone.utc
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _run(tmp_path, *, config_path=None, ledger_path=None, codex_sessions_dir=None, now=NOW):
    return run_doctor(
        config_path=config_path or tmp_path / "config.json",
        ledger_path=ledger_path or tmp_path / "ledger.sqlite3",
        hermes_db=tmp_path / "missing-hermes.db",
        claude_projects_dir=tmp_path / "missing-claude",
        codex_sessions_dir=codex_sessions_dir or tmp_path / "missing-codex",
        now=now,
    )


def _write_codex_activity(tmp_path, *, timestamp="2026-07-10T10:00:00+00:00"):
    sessions_dir = tmp_path / "codex_sessions"
    write_rollout(
        sessions_dir / "session-a" / "rollout-1.jsonl",
        "session-a",
        [token_count_event(timestamp, total_input=100, total_output=50, total_reasoning=0)],
    )
    return sessions_dir


def test_doctor_reports_repo_target_and_a_stable_device_id(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    save_config(config_path, AppConfig(repo_target="tmdqja75/tmdqja75"))

    report = _run(tmp_path, config_path=config_path)

    assert report.repo_target == "tmdqja75/tmdqja75"
    assert len(report.device_id) == 36


def test_doctor_reports_no_repo_target_when_unset(tmp_path) -> None:
    report = _run(tmp_path)

    assert report.repo_target is None


def test_doctor_reports_unavailable_for_missing_sources(tmp_path) -> None:
    report = _run(tmp_path)

    for source in report.sources:
        assert source.status is SourceStatus.SOURCE_UNAVAILABLE


def test_doctor_reports_activity_when_a_source_has_usage(tmp_path) -> None:
    codex_sessions_dir = _write_codex_activity(tmp_path)

    report = _run(tmp_path, codex_sessions_dir=codex_sessions_dir)

    codex_source = next(s for s in report.sources if s.agent is SupportedAgent.CODEX)
    assert codex_source.status is SourceStatus.AVAILABLE_WITH_ACTIVITY


def test_doctor_never_writes_ledger_events_or_moves_checkpoints(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    codex_sessions_dir = _write_codex_activity(tmp_path)

    _run(tmp_path, ledger_path=ledger_path, codex_sessions_dir=codex_sessions_dir)

    repository = LedgerRepository.open(ledger_path)
    try:
        assert repository.list_records() == []
        assert repository.get_checkpoint(SupportedAgent.CODEX) is None
    finally:
        repository.close()


def test_doctor_report_surfaces_the_configured_initial_collection_start(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    save_config(config_path, AppConfig(initial_collection_start="2026-01-01"))

    report = _run(tmp_path, config_path=config_path)

    assert report.initial_collection_start == "2026-01-01"


def test_doctor_report_defaults_initial_collection_start_to_none(tmp_path) -> None:
    report = _run(tmp_path)

    assert report.initial_collection_start is None


def test_doctor_report_surfaces_the_configured_bar_chart_threshold_days(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    save_config(config_path, AppConfig(bar_chart_threshold_days=5))

    report = _run(tmp_path, config_path=config_path)

    assert report.bar_chart_threshold_days == 5


def test_doctor_report_defaults_bar_chart_threshold_days_to_15(tmp_path) -> None:
    report = _run(tmp_path)

    assert report.bar_chart_threshold_days == 15


def test_doctor_device_id_is_stable_across_runs(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"

    first = _run(tmp_path, config_path=config_path, ledger_path=ledger_path)
    second = _run(tmp_path, config_path=config_path, ledger_path=ledger_path)

    assert first.device_id == second.device_id
