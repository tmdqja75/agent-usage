from datetime import date
from pathlib import Path

from tomax.commands import render as render_command


def test_render_writes_screenshot_and_readme(tmp_path, monkeypatch):
    calls = {"export": 0}

    def fake_export(output_path, **kwargs):
        calls["export"] += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    monkeypatch.setattr(render_command, "export_dashboard_png", fake_export)

    out = tmp_path / "preview"
    ledger = tmp_path / "ledger.sqlite3"
    result = render_command.render(
        ledger_path=ledger,
        output_dir=out,
        today=date(2026, 7, 24),
        generated_at="2026-07-24 00:00 UTC",
        ui_dir=Path("dashboard-ui"),
        tmp_stage_dir=tmp_path / "stage",
    )

    assert calls["export"] == 1
    assert (out / "assets" / "tomax" / "dashboard.png").is_file()
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "assets/tomax/dashboard.png" in readme
    assert result.changed is True


def test_render_idempotent_second_run(tmp_path, monkeypatch):
    def fake_export(output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    monkeypatch.setattr(render_command, "export_dashboard_png", fake_export)

    out = tmp_path / "preview"
    kwargs = dict(
        ledger_path=tmp_path / "ledger.sqlite3",
        output_dir=out,
        today=date(2026, 7, 24),
        generated_at="2026-07-24 00:00 UTC",
        ui_dir=Path("dashboard-ui"),
        tmp_stage_dir=tmp_path / "stage",
    )
    render_command.render(**kwargs)
    second = render_command.render(**kwargs)
    assert second.changed is False
