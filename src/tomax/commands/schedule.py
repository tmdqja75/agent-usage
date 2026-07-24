"""Local orchestration for the opt-in macOS daily scheduler command.

Wraps ``tomax.schedule.launchd`` with the local config update that
keeps ``AppConfig.schedule_enabled``/``schedule_time`` in sync with
whatever plist actually exists, so ``doctor`` and other commands can read
schedule state from config without re-probing launchd.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from tomax.config import load_config, save_config
from tomax.schedule import launchd
from tomax.schedule.launchd import CommandRunner, ScheduleStatus


@dataclass(frozen=True, slots=True)
class ScheduleInstallResult:
    plist_path: Path
    daily_at: str


def install(
    *,
    config_path: Path,
    daily_at: str,
    executable: str,
    log_dir: Path,
    runner: CommandRunner = launchd.default_runner,
) -> ScheduleInstallResult:
    """Install the daily LaunchAgent and record it in local config.

    Validates ``daily_at`` via ``AppConfig`` before touching launchd at
    all, so a malformed time never leaves a stray plist behind.
    """
    config = replace(load_config(config_path), schedule_enabled=True, schedule_time=daily_at)
    target = launchd.install(executable=executable, daily_at=daily_at, log_dir=log_dir, runner=runner)
    save_config(config_path, config)
    return ScheduleInstallResult(plist_path=target, daily_at=daily_at)


def remove(*, config_path: Path, runner: CommandRunner = launchd.default_runner) -> bool:
    """Unload and delete the LaunchAgent, clearing schedule state from local config."""
    removed = launchd.remove(runner=runner)
    config = replace(load_config(config_path), schedule_enabled=False, schedule_time=None)
    save_config(config_path, config)
    return removed


def status(*, runner: CommandRunner = launchd.default_runner) -> ScheduleStatus:
    """Report whether the daily LaunchAgent is installed and currently loaded."""
    return launchd.status(runner=runner)
