"""Tests for the local dashboard preview command."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from tomax.commands import render as render_command
from tomax.commands.render import render
from tomax.ledger.repository import LedgerRepository
from tomax.models import NormalizedUsageRecord, SourceStatus, SupportedAgent, TokenUsage

UTC = timezone.utc
TODAY = date(2026, 7, 18)
GENERATED_AT = "2026-07-18 00:00 UTC"


def _insert_record(ledger_path, **overrides) -> None:
    defaults = dict(
        agent=SupportedAgent.CLAUDE_CODE,
        occurred_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
        fingerprint="fp-1",
        session_fingerprint="s-1",
        tokens=TokenUsage(input_tokens=10, output_tokens=5),
    )
    defaults.update(overrides)
    record = NormalizedUsageRecord(**defaults)
    repository = LedgerRepository.open(ledger_path)
    try:
        repository.insert_records([record])
    finally:
        repository.close()


def _fake_export(output_path, **kwargs):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")


def _render(monkeypatch, tmp_path, **kwargs):
    monkeypatch.setattr(render_command, "export_dashboard_png", _fake_export)
    kwargs.setdefault("ui_dir", Path("dashboard-ui"))
    kwargs.setdefault("tmp_stage_dir", tmp_path / "stage")
    return render(**kwargs)


def test_render_writes_a_readme_and_dashboard_screenshot(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(ledger_path)
    output_dir = tmp_path / "preview"

    result = _render(
        monkeypatch,
        tmp_path,
        ledger_path=ledger_path,
        output_dir=output_dir,
        today=TODAY,
        generated_at=GENERATED_AT,
    )

    assert result.changed is True
    assert result.readme_path.exists()
    readme = result.readme_path.read_text(encoding="utf-8")
    assert "tomax:start" in readme
    assert "assets/tomax/dashboard.png" in readme
    assert (output_dir / "assets" / "tomax" / "dashboard.png").exists()


def test_render_honors_a_custom_pie_top_n(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(ledger_path)
    output_dir = tmp_path / "preview"

    result = _render(
        monkeypatch,
        tmp_path,
        ledger_path=ledger_path,
        output_dir=output_dir,
        today=TODAY,
        generated_at=GENERATED_AT,
        pie_top_n=1,
    )

    assert result.changed is True


def test_render_stages_a_public_daily_record_for_this_device(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(ledger_path)
    output_dir = tmp_path / "preview"

    result = _render(
        monkeypatch,
        tmp_path,
        ledger_path=ledger_path,
        output_dir=output_dir,
        today=TODAY,
        generated_at=GENERATED_AT,
    )

    staged = output_dir / "data" / "v1" / "devices" / result.device_id / "2026-07-10.json"
    assert staged.exists()


def test_render_is_idempotent_on_unchanged_ledger_data(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(ledger_path)
    output_dir = tmp_path / "preview"
    kwargs = dict(
        ledger_path=ledger_path, output_dir=output_dir, today=TODAY, generated_at=GENERATED_AT
    )

    first = _render(monkeypatch, tmp_path, **kwargs)
    second = _render(monkeypatch, tmp_path, **kwargs)

    assert first.changed is True
    assert second.changed is False


def test_render_handles_an_empty_ledger_without_crashing(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    output_dir = tmp_path / "preview"

    result = _render(
        monkeypatch,
        tmp_path,
        ledger_path=ledger_path,
        output_dir=output_dir,
        today=TODAY,
        generated_at=GENERATED_AT,
    )

    assert "## Agent Usage" in result.readme_path.read_text(encoding="utf-8")


def test_render_applies_the_privacy_policy_to_skill_and_mcp_names(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(
        ledger_path,
        fingerprint="fp-secret-tool",
        session_fingerprint=None,
        tokens=TokenUsage(),
        observed_skill_name="my-api-key-tool",
        source_status=SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY,
    )
    output_dir = tmp_path / "preview"

    _render(
        monkeypatch,
        tmp_path,
        ledger_path=ledger_path,
        output_dir=output_dir,
        today=TODAY,
        generated_at=GENERATED_AT,
    )

    staged_files = list((output_dir / "data" / "v1" / "devices").glob("*/2026-07-10.json"))
    assert staged_files
    content = staged_files[0].read_text(encoding="utf-8")
    assert "my-api-key-tool" not in content
    assert "(hidden)" in content


def test_render_preserves_existing_readme_content_outside_the_markers(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    _insert_record(ledger_path)
    output_dir = tmp_path / "preview"
    output_dir.mkdir(parents=True)
    (output_dir / "README.md").write_text("# My Profile\n\nIntro text.\n", encoding="utf-8")

    result = _render(
        monkeypatch,
        tmp_path,
        ledger_path=ledger_path,
        output_dir=output_dir,
        today=TODAY,
        generated_at=GENERATED_AT,
    )

    text = result.readme_path.read_text(encoding="utf-8")
    assert "# My Profile" in text
    assert "Intro text." in text
