"""Tests for the schedule command: config updates plus launchd install/status/remove.

Every test monkeypatches ``launch_agents_dir`` to a tmp_path and passes a
fake ``runner``, so this suite never touches the real launchd — same
constraint as ``tests/schedule/test_launchd.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_usage.commands import schedule as schedule_command
from agent_usage.config import load_config
from agent_usage.schedule import launchd


def _fake_runner(returncode: int = 0):
    def runner(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, returncode, stdout="", stderr="")

    return runner


def test_install_marks_the_schedule_enabled_in_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(launchd, "launch_agents_dir", lambda: tmp_path / "LaunchAgents")
    config_path = tmp_path / "config.json"

    result = schedule_command.install(
        config_path=config_path,
        daily_at="09:00",
        executable="agent-usage",
        log_dir=tmp_path / "logs",
        runner=_fake_runner(),
    )

    assert result.daily_at == "09:00"
    assert result.plist_path.exists()
    config = load_config(config_path)
    assert config.schedule_enabled is True
    assert config.schedule_time == "09:00"


def test_install_does_not_enable_config_when_launchctl_load_fails(tmp_path: Path, monkeypatch) -> None:
    import pytest

    monkeypatch.setattr(launchd, "launch_agents_dir", lambda: tmp_path / "LaunchAgents")
    config_path = tmp_path / "config.json"

    with pytest.raises(launchd.LaunchctlError):
        schedule_command.install(
            config_path=config_path,
            daily_at="09:00",
            executable="agent-usage",
            log_dir=tmp_path / "logs",
            runner=_fake_runner(returncode=1),
        )

    assert not config_path.exists()


def test_install_rejects_a_malformed_time_without_writing_a_plist(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(launchd, "launch_agents_dir", lambda: tmp_path / "LaunchAgents")
    config_path = tmp_path / "config.json"

    import pytest

    with pytest.raises(ValueError):
        schedule_command.install(
            config_path=config_path,
            daily_at="9am",
            executable="agent-usage",
            log_dir=tmp_path / "logs",
            runner=_fake_runner(),
        )

    assert not (tmp_path / "LaunchAgents").exists()
    assert not config_path.exists()


def test_remove_marks_the_schedule_disabled_in_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(launchd, "launch_agents_dir", lambda: tmp_path / "LaunchAgents")
    config_path = tmp_path / "config.json"
    schedule_command.install(
        config_path=config_path,
        daily_at="09:00",
        executable="agent-usage",
        log_dir=tmp_path / "logs",
        runner=_fake_runner(),
    )

    removed = schedule_command.remove(config_path=config_path, runner=_fake_runner())

    assert removed is True
    config = load_config(config_path)
    assert config.schedule_enabled is False
    assert config.schedule_time is None


def test_remove_does_not_disable_config_when_launchctl_unload_fails(tmp_path: Path, monkeypatch) -> None:
    import pytest

    monkeypatch.setattr(launchd, "launch_agents_dir", lambda: tmp_path / "LaunchAgents")
    config_path = tmp_path / "config.json"
    schedule_command.install(
        config_path=config_path,
        daily_at="09:00",
        executable="agent-usage",
        log_dir=tmp_path / "logs",
        runner=_fake_runner(),
    )

    with pytest.raises(launchd.LaunchctlError):
        schedule_command.remove(config_path=config_path, runner=_fake_runner(returncode=1))

    config = load_config(config_path)
    assert config.schedule_enabled is True
    assert config.schedule_time == "09:00"


def test_remove_preserves_other_config_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(launchd, "launch_agents_dir", lambda: tmp_path / "LaunchAgents")
    config_path = tmp_path / "config.json"
    from agent_usage.config import AppConfig, save_config

    save_config(config_path, AppConfig(repo_target="tmdqja75/tmdqja75"))
    schedule_command.install(
        config_path=config_path,
        daily_at="09:00",
        executable="agent-usage",
        log_dir=tmp_path / "logs",
        runner=_fake_runner(),
    )

    schedule_command.remove(config_path=config_path, runner=_fake_runner())

    config = load_config(config_path)
    assert config.repo_target == "tmdqja75/tmdqja75"


def test_status_reflects_the_launchd_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(launchd, "launch_agents_dir", lambda: tmp_path / "LaunchAgents")
    config_path = tmp_path / "config.json"
    schedule_command.install(
        config_path=config_path,
        daily_at="09:00",
        executable="agent-usage",
        log_dir=tmp_path / "logs",
        runner=_fake_runner(),
    )

    result = schedule_command.status(runner=_fake_runner(returncode=0))

    assert result.installed is True
    assert result.loaded is True
    assert result.daily_at == "09:00"
