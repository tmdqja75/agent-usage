from datetime import date

import pytest

from agent_usage.commands import dashboard as dashboard_command
from agent_usage.dashboard.remote import NoRepoTargetError


def test_run_builds_payload_and_serves(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setattr(
        dashboard_command, "build_payload", lambda **kwargs: {"served": kwargs["all_devices"]}
    )
    monkeypatch.setattr(
        dashboard_command, "ensure_build", lambda ui_dir, *, force: ui_dir / "dist"
    )

    def fake_serve(data, *, dist_dir, port, open_browser):
        calls["data"] = data
        calls["dist_dir"] = dist_dir
        calls["port"] = port
        calls["open_browser"] = open_browser

    monkeypatch.setattr(dashboard_command, "serve", fake_serve)

    ui_dir = tmp_path / "dashboard-ui"
    ui_dir.mkdir()

    dashboard_command.run(
        ledger_path=tmp_path / "ledger.sqlite3",
        config_path=tmp_path / "config.json",
        all_devices=True,
        port=8123,
        open_browser=False,
        pie_top_n=6,
        ui_dir=ui_dir,
        force_build=False,
        today=date(2026, 7, 18),
        tmp_stage_dir=tmp_path / "stage",
    )

    assert calls["data"] == {"served": True}
    assert calls["dist_dir"] == ui_dir / "dist"
    assert calls["port"] == 8123
    assert calls["open_browser"] is False


def test_run_reports_missing_repo_target(monkeypatch, tmp_path):
    def boom(**kwargs):
        raise NoRepoTargetError("no repo target set")

    monkeypatch.setattr(dashboard_command, "build_payload", boom)
    monkeypatch.setattr(dashboard_command, "ensure_build", lambda ui_dir, *, force: ui_dir)
    monkeypatch.setattr(dashboard_command, "serve", lambda *a, **k: None)

    ui_dir = tmp_path / "dashboard-ui"
    ui_dir.mkdir()

    with pytest.raises(dashboard_command.DashboardError):
        dashboard_command.run(
            ledger_path=tmp_path / "ledger.sqlite3",
            config_path=tmp_path / "config.json",
            all_devices=True,
            port=8000,
            open_browser=False,
            pie_top_n=6,
            ui_dir=ui_dir,
            force_build=False,
            today=date(2026, 7, 18),
            tmp_stage_dir=tmp_path / "stage",
        )
