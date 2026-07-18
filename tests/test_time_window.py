"""Tests for deterministic UTC collection windows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_usage.time_window import INITIAL_COLLECTION_WINDOW, TimeWindow, normalize_utc


UTC = timezone.utc


def test_initial_collection_window_is_exactly_two_week_half_open_interval() -> None:
    window = INITIAL_COLLECTION_WINDOW

    assert window.start_utc == datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
    assert window.end_utc == datetime(2026, 7, 18, 0, 0, tzinfo=UTC)
    assert window.end_utc - window.start_utc == timedelta(days=14)
    assert window.contains(datetime(2026, 7, 4, 0, 0, tzinfo=UTC))
    assert window.contains(datetime(2026, 7, 17, 23, 59, 59, 999999, tzinfo=UTC))
    assert not window.contains(datetime(2026, 7, 3, 23, 59, 59, 999999, tzinfo=UTC))
    assert not window.contains(datetime(2026, 7, 18, 0, 0, tzinfo=UTC))


def test_window_normalizes_offset_inputs_before_membership_check() -> None:
    assert INITIAL_COLLECTION_WINDOW.contains(
        datetime(2026, 7, 4, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    )


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
    with pytest.raises(ValueError, match="timezone-aware"):
        INITIAL_COLLECTION_WINDOW.contains(datetime(2026, 7, 4))
