"""Deterministic UTC time-window helpers for local usage collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC = timezone.utc


def normalize_utc(value: datetime) -> datetime:
    """Return an aware timestamp normalized to the UTC public-time basis."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("time inputs must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A half-open UTC window with an independent IANA display timezone."""

    start: datetime
    end: datetime
    display_timezone: str = "UTC"
    _display_zone: ZoneInfo = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        start_utc = normalize_utc(self.start)
        end_utc = normalize_utc(self.end)
        if start_utc >= end_utc:
            raise ValueError("window end must be after window start")

        try:
            display_zone = ZoneInfo(self.display_timezone)
        except (TypeError, ZoneInfoNotFoundError) as error:
            raise ValueError("display_timezone must be a valid IANA timezone name") from error

        object.__setattr__(self, "start", start_utc)
        object.__setattr__(self, "end", end_utc)
        object.__setattr__(self, "_display_zone", display_zone)

    @property
    def start_utc(self) -> datetime:
        """The public UTC start boundary, included in the interval."""
        return self.start

    @property
    def end_utc(self) -> datetime:
        """The public UTC end boundary, excluded from the interval."""
        return self.end

    @property
    def display_zone(self) -> ZoneInfo:
        """The separately configured IANA timezone for presentation only."""
        return self._display_zone

    def contains(self, occurred_at: datetime) -> bool:
        """Return whether an aware instant lies in this half-open UTC interval."""
        instant_utc = normalize_utc(occurred_at)
        return self.start <= instant_utc < self.end


DEFAULT_INITIAL_START = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
"""Default first-run collection start when no config override is set."""

EPOCH_START = datetime(1970, 1, 1, 0, 0, tzinfo=UTC)
"""Sentinel start used to request unbounded ('ALL') history backfill."""
