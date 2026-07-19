"""Tests for CLI command wiring."""

from __future__ import annotations

from typer.testing import CliRunner

import agent_usage.cli as cli_module
from agent_usage.cli import app

runner = CliRunner()


def _patch_local_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_module, "config_file_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(cli_module, "ledger_file_path", lambda: tmp_path / "ledger.sqlite3")


def _patch_missing_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_module, "DEFAULT_HERMES_STATE_DB", tmp_path / "missing-hermes.db")
    monkeypatch.setattr(
        cli_module, "DEFAULT_CLAUDE_CODE_PROJECTS_DIR", tmp_path / "missing-claude"
    )
    monkeypatch.setattr(cli_module, "DEFAULT_CODEX_SESSIONS_DIR", tmp_path / "missing-codex")


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for name in ("init", "doctor", "collect", "render"):
        assert name in result.stdout


def test_init_command_sets_repo_target(tmp_path, monkeypatch) -> None:
    _patch_local_paths(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init", "--repo", "tmdqja75/tmdqja75"])

    assert result.exit_code == 0
    assert "tmdqja75/tmdqja75" in result.stdout


def test_init_command_rejects_a_malformed_repo_target(tmp_path, monkeypatch) -> None:
    _patch_local_paths(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init", "--repo", "not-valid"])

    assert result.exit_code != 0


def test_doctor_command_reports_unavailable_sources_with_no_real_sources_present(
    tmp_path, monkeypatch
) -> None:
    _patch_local_paths(monkeypatch, tmp_path)
    _patch_missing_sources(monkeypatch, tmp_path)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "source_unavailable" in result.stdout
    assert "device id" in result.stdout


def test_collect_dry_run_reports_and_writes_nothing(tmp_path, monkeypatch) -> None:
    _patch_local_paths(monkeypatch, tmp_path)
    _patch_missing_sources(monkeypatch, tmp_path)

    result = runner.invoke(app, ["collect", "--dry-run"])

    assert result.exit_code == 0
    assert "dry run" in result.stdout.lower()
    ledger_path = tmp_path / "ledger.sqlite3"
    if ledger_path.exists():
        from agent_usage.ledger.repository import LedgerRepository

        repository = LedgerRepository.open(ledger_path)
        try:
            assert repository.list_records() == []
        finally:
            repository.close()


def test_collect_then_render_produces_a_local_preview(tmp_path, monkeypatch) -> None:
    _patch_local_paths(monkeypatch, tmp_path)
    _patch_missing_sources(monkeypatch, tmp_path)

    collect_result = runner.invoke(app, ["collect"])
    assert collect_result.exit_code == 0

    output_dir = tmp_path / "preview"
    render_result = runner.invoke(app, ["render", "--output-dir", str(output_dir)])

    assert render_result.exit_code == 0
    assert (output_dir / "README.md").exists()
