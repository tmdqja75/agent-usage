"""Tests for private local configuration and opaque device identity."""

from __future__ import annotations

import json

import pytest

from datetime import datetime, timezone

from agent_usage.config import (
    AppConfig,
    config_dir,
    config_file_path,
    data_dir,
    get_or_create_device_id,
    ledger_file_path,
    load_config,
    resolve_initial_collection_start,
    save_config,
)
from agent_usage.time_window import DEFAULT_INITIAL_START, EPOCH_START

UTC = timezone.utc


def test_config_dir_and_data_dir_are_scoped_to_this_app() -> None:
    assert "agent-usage" in str(config_dir()).lower()
    assert "agent-usage" in str(data_dir()).lower()


def test_config_file_and_ledger_file_paths_live_under_their_app_dirs() -> None:
    assert config_file_path().parent == config_dir()
    assert ledger_file_path().parent == data_dir()


def test_default_config_has_no_repo_target_and_utc_timezone() -> None:
    config = AppConfig()

    assert config.repo_target is None
    assert config.display_timezone == "UTC"
    assert config.privacy_allow == ()
    assert config.privacy_block == ()
    assert config.schedule_enabled is False
    assert config.schedule_time is None


@pytest.mark.parametrize(
    "bad_repo_target",
    ["", "no-slash", "a/b/c", "owner/", "/repo", "owner:token@host/repo"],
)
def test_config_rejects_malformed_repo_target(bad_repo_target: str) -> None:
    with pytest.raises(ValueError, match="repo_target"):
        AppConfig(repo_target=bad_repo_target)


def test_config_accepts_a_well_formed_repo_target() -> None:
    config = AppConfig(repo_target="tmdqja75/tmdqja75")

    assert config.repo_target == "tmdqja75/tmdqja75"


def test_config_rejects_an_invalid_display_timezone() -> None:
    with pytest.raises(ValueError, match="IANA"):
        AppConfig(display_timezone="not/a-timezone")


@pytest.mark.parametrize("bad_schedule_time", ["9:00", "25:00", "09:60", "0900", "noon"])
def test_config_rejects_a_malformed_schedule_time(bad_schedule_time: str) -> None:
    with pytest.raises(ValueError, match="schedule_time"):
        AppConfig(schedule_enabled=True, schedule_time=bad_schedule_time)


def test_config_accepts_a_well_formed_schedule_time() -> None:
    config = AppConfig(schedule_enabled=True, schedule_time="09:00")

    assert config.schedule_time == "09:00"


def test_config_rejects_schedule_enabled_without_a_schedule_time() -> None:
    with pytest.raises(ValueError, match="schedule_time"):
        AppConfig(schedule_enabled=True, schedule_time=None)


def test_save_and_load_config_round_trips(tmp_path) -> None:
    path = tmp_path / "config.json"
    config = AppConfig(
        repo_target="tmdqja75/tmdqja75",
        privacy_allow=("safe-skill",),
        privacy_block=("internal-tool",),
        display_timezone="America/Los_Angeles",
        schedule_enabled=True,
        schedule_time="09:00",
    )

    save_config(path, config)
    loaded = load_config(path)

    assert loaded == config


def test_load_config_returns_defaults_when_file_is_absent(tmp_path) -> None:
    loaded = load_config(tmp_path / "missing-config.json")

    assert loaded == AppConfig()


def test_saved_config_contains_no_github_token_hostname_or_agent_path(tmp_path) -> None:
    path = tmp_path / "config.json"
    save_config(
        path,
        AppConfig(
            repo_target="tmdqja75/tmdqja75",
            privacy_allow=("safe-skill",),
            display_timezone="UTC",
        ),
    )

    raw = json.loads(path.read_text())

    forbidden_keys = {"token", "github_token", "hostname", "host", "agent_path", "path"}
    assert not forbidden_keys & set(raw.keys())

    serialized = json.dumps(raw)
    assert "ghp_" not in serialized
    assert "/Users/" not in serialized
    assert "/home/" not in serialized


def test_get_or_create_device_id_is_a_random_uuid(tmp_path) -> None:
    device_id = get_or_create_device_id(tmp_path / "ledger.sqlite3")

    assert len(device_id) == 36
    assert device_id.count("-") == 4


def test_get_or_create_device_id_is_stable_across_calls(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"

    first = get_or_create_device_id(ledger_path)
    second = get_or_create_device_id(ledger_path)

    assert first == second


def test_get_or_create_device_id_differs_across_separate_installs(tmp_path) -> None:
    first = get_or_create_device_id(tmp_path / "install-one.sqlite3")
    second = get_or_create_device_id(tmp_path / "install-two.sqlite3")

    assert first != second


def test_get_or_create_device_id_works_on_a_fresh_install_with_no_app_dir_yet(
    tmp_path,
) -> None:
    fresh_install_path = tmp_path / "Application Support" / "agent-usage" / "ledger.sqlite3"

    device_id = get_or_create_device_id(fresh_install_path)

    assert fresh_install_path.exists()
    assert len(device_id) == 36


def test_default_config_has_no_initial_collection_start_override() -> None:
    config = AppConfig()

    assert config.initial_collection_start is None


@pytest.mark.parametrize("bad_value", ["", "not-a-date", "2026/07/04", "2026-13-40"])
def test_config_rejects_malformed_initial_collection_start(bad_value: str) -> None:
    with pytest.raises(ValueError, match="initial_collection_start"):
        AppConfig(initial_collection_start=bad_value)


def test_config_accepts_all_and_a_well_formed_iso_date_for_initial_collection_start() -> None:
    assert AppConfig(initial_collection_start="ALL").initial_collection_start == "ALL"
    assert (
        AppConfig(initial_collection_start="2026-01-01").initial_collection_start
        == "2026-01-01"
    )


def test_resolve_initial_collection_start_none_uses_the_default() -> None:
    assert resolve_initial_collection_start(None) == DEFAULT_INITIAL_START


def test_resolve_initial_collection_start_all_is_unbounded() -> None:
    assert resolve_initial_collection_start("ALL") == EPOCH_START


def test_resolve_initial_collection_start_parses_a_custom_iso_date() -> None:
    assert resolve_initial_collection_start("2026-01-01") == datetime(2026, 1, 1, tzinfo=UTC)


def test_default_config_has_a_bar_chart_threshold_of_15_days() -> None:
    config = AppConfig()

    assert config.bar_chart_threshold_days == 15


@pytest.mark.parametrize("bad_value", [0, -1, -15])
def test_config_rejects_non_positive_bar_chart_threshold_days(bad_value: int) -> None:
    with pytest.raises(ValueError, match="bar_chart_threshold_days"):
        AppConfig(bar_chart_threshold_days=bad_value)


def test_config_accepts_a_custom_bar_chart_threshold_days() -> None:
    assert AppConfig(bar_chart_threshold_days=5).bar_chart_threshold_days == 5
