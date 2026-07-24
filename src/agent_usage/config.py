"""Private local configuration and opaque device identity.

Holds only user preferences safe to keep on disk: a repo target, privacy
name overrides, a display timezone, and scheduling preferences. Never holds
GitHub tokens, hostnames, or raw agent source paths.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from platformdirs import PlatformDirs

from agent_usage.ledger.repository import LedgerRepository
from agent_usage.time_window import DEFAULT_INITIAL_START, EPOCH_START, UTC

APP_NAME = "agent-usage"

_REPO_TARGET_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SCHEDULE_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_initial_collection_start(value: str | None) -> None:
    if value is None or value == "ALL":
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(
            "initial_collection_start must be None, 'ALL', or an ISO date (YYYY-MM-DD)"
        ) from error


def _validate_bar_chart_threshold_days(value: int) -> None:
    if value < 1:
        raise ValueError("bar_chart_threshold_days must be a positive integer")


def _app_dirs() -> PlatformDirs:
    return PlatformDirs(appname=APP_NAME)


def config_dir() -> Path:
    """The local, private directory holding this install's configuration."""
    return Path(_app_dirs().user_config_dir)


def data_dir() -> Path:
    """The local, private directory holding this install's ledger database."""
    return Path(_app_dirs().user_data_dir)


def config_file_path() -> Path:
    """The default path to this install's configuration file."""
    return config_dir() / "config.json"


def ledger_file_path() -> Path:
    """The default path to this install's private SQLite ledger."""
    return data_dir() / "ledger.sqlite3"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Local user preferences with no secrets, hostnames, or agent paths."""

    repo_target: str | None = None
    privacy_allow: tuple[str, ...] = ()
    privacy_block: tuple[str, ...] = ()
    display_timezone: str = "UTC"
    initial_collection_start: str | None = None
    bar_chart_threshold_days: int = 15
    schedule_enabled: bool = False
    schedule_time: str | None = None

    def __post_init__(self) -> None:
        if self.repo_target is not None and not _REPO_TARGET_PATTERN.match(
            self.repo_target
        ):
            raise ValueError("repo_target must be in OWNER/REPO form")

        try:
            ZoneInfo(self.display_timezone)
        except (TypeError, ZoneInfoNotFoundError) as error:
            raise ValueError(
                "display_timezone must be a valid IANA timezone name"
            ) from error

        _validate_initial_collection_start(self.initial_collection_start)

        _validate_bar_chart_threshold_days(self.bar_chart_threshold_days)

        if self.schedule_time is not None and not _SCHEDULE_TIME_PATTERN.match(
            self.schedule_time
        ):
            raise ValueError("schedule_time must be in 24-hour HH:MM form")

        if self.schedule_enabled and self.schedule_time is None:
            raise ValueError("schedule_time is required when schedule_enabled is True")

    def to_dict(self) -> dict:
        """Serialize to a plain dict safe to write as public-adjacent local JSON."""
        data = asdict(self)
        data["privacy_allow"] = list(self.privacy_allow)
        data["privacy_block"] = list(self.privacy_block)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        return cls(
            repo_target=data.get("repo_target"),
            privacy_allow=tuple(data.get("privacy_allow", ())),
            privacy_block=tuple(data.get("privacy_block", ())),
            display_timezone=data.get("display_timezone", "UTC"),
            initial_collection_start=data.get("initial_collection_start"),
            bar_chart_threshold_days=data.get("bar_chart_threshold_days", 15),
            schedule_enabled=data.get("schedule_enabled", False),
            schedule_time=data.get("schedule_time"),
        )


def load_config(path: Path) -> AppConfig:
    """Load configuration from disk, or return defaults if no file exists yet."""
    if not path.exists():
        return AppConfig()
    return AppConfig.from_dict(json.loads(path.read_text()))


def save_config(path: Path, config: AppConfig) -> None:
    """Persist configuration to disk as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n")


def resolve_initial_collection_start(value: str | None) -> datetime:
    """Resolve a config's ``initial_collection_start`` to a concrete UTC datetime."""
    if value is None:
        return DEFAULT_INITIAL_START
    if value == "ALL":
        return EPOCH_START
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def get_or_create_device_id(ledger_path: Path) -> str:
    """Return this install's opaque device identifier from the private ledger."""
    repository = LedgerRepository.open(ledger_path)
    try:
        return repository.get_or_create_device_id()
    finally:
        repository.close()
