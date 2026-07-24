"""Tests for deterministic UTC collection windows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_usage.time_window import DEFAULT_INITIAL_START, EPOCH_START, TimeWindow, normalize_utc


UTC = timezone.utc


def test_default_initial_start_is_the_2026_07_04_backfill_date() -> None:
    assert DEFAULT_INITIAL_START == datetime(2026, 7, 4, 0, 0, tzinfo=UTC)


def test_epoch_start_is_unix_epoch_for_unbounded_all_history_backfill() -> None:
    assert EPOCH_START == datetime(1970, 1, 1, tzinfo=UTC)


def test_window_normalizes_offset_inputs_before_membership_check() -> None:
    window = TimeWindow(
        start=datetime(2026, 7, 4, tzinfo=UTC),
        end=datetime(2026, 7, 18, tzinfo=UTC),
    )
    assert window.contains(datetime(2026, 7, 4, 9, 0, tzinfo=timezone(timedelta(hours=9))))


def test_window_uses_utc_public_boundaries_with_separate_iana_display_timezone() -> None:
    window = TimeWindow(
        start=datetime(2026, 7, 4, tzinfo=UTC),
        end=datetime(2026, 7, 18, tzinfo=UTC),
        display_timezone="America/Los_Angeles",
    )

    assert window.start_utc.tzinfo is UTC
    assert window.end_utc.tzinfo is UTC
    assert window.display_timezone == "America/Los_Angeles"
    assert window.display_zone.key == "America/Los_Angeles"


@pytest.mark.parametrize("value", [datetime(2026, 7, 4), datetime(2026, 7, 18)])
def test_time_inputs_must_be_timezone_aware(value: datetime) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_utc(value)

    with pytest.raises(ValueError, match="timezone-aware"):
        TimeWindow(
            start=value,
            end=datetime(2026, 7, 18, tzinfo=UTC),
            display_timezone="UTC",
        )


def test_window_rejects_invalid_display_timezone_and_non_positive_interval() -> None:
    with pytest.raises(ValueError, match="IANA"):
        TimeWindow(
            start=datetime(2026, 7, 4, tzinfo=UTC),
            end=datetime(2026, 7, 18, tzinfo=UTC),
            display_timezone="not/a-timezone",
        )

    with pytest.raises(ValueError, match="after"):
        TimeWindow(
            start=datetime(2026, 7, 18, tzinfo=UTC),
            end=datetime(2026, 7, 4, tzinfo=UTC),
            display_timezone="UTC",
        )


def test_window_rejects_naive_membership_timestamp() -> None:
    window = TimeWindow(
        start=datetime(2026, 7, 4, tzinfo=UTC),
        end=datetime(2026, 7, 18, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        window.contains(datetime(2026, 7, 4))
