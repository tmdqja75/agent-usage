"""Tests for local, network-free profile-repo setup."""

from __future__ import annotations

import pytest

from tomax.commands.init import init
from tomax.config import AppConfig, get_or_create_device_id, load_config, save_config


def test_init_sets_repo_target(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"

    config = init("tmdqja75/tmdqja75", config_path=config_path, ledger_path=ledger_path)

    assert config.repo_target == "tmdqja75/tmdqja75"
    assert load_config(config_path).repo_target == "tmdqja75/tmdqja75"


def test_init_creates_the_local_ledger_and_a_device_id(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"

    init("tmdqja75/tmdqja75", config_path=config_path, ledger_path=ledger_path)

    assert ledger_path.exists()
    device_id = get_or_create_device_id(ledger_path)
    assert len(device_id) == 36


def test_init_preserves_other_existing_config_fields(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"
    save_config(
        config_path,
        AppConfig(display_timezone="America/Los_Angeles", privacy_allow=("safe-skill",)),
    )

    config = init("tmdqja75/tmdqja75", config_path=config_path, ledger_path=ledger_path)

    assert config.display_timezone == "America/Los_Angeles"
    assert config.privacy_allow == ("safe-skill",)


def test_init_rejects_a_malformed_repo_target(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"

    with pytest.raises(ValueError, match="repo_target"):
        init("not-a-valid-target", config_path=config_path, ledger_path=ledger_path)


def test_init_does_not_write_a_config_file_when_the_repo_target_is_invalid(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"

    with pytest.raises(ValueError):
        init("not-a-valid-target", config_path=config_path, ledger_path=ledger_path)

    assert not config_path.exists()


def test_init_run_twice_does_not_change_the_device_id(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"

    init("tmdqja75/tmdqja75", config_path=config_path, ledger_path=ledger_path)
    first_device_id = get_or_create_device_id(ledger_path)
    init("tmdqja75/tmdqja75", config_path=config_path, ledger_path=ledger_path)
    second_device_id = get_or_create_device_id(ledger_path)

    assert first_device_id == second_device_id


def test_init_never_writes_a_github_token_or_hostname(tmp_path) -> None:
    import json

    config_path = tmp_path / "config.json"
    ledger_path = tmp_path / "ledger.sqlite3"

    init("tmdqja75/tmdqja75", config_path=config_path, ledger_path=ledger_path)

    serialized = json.dumps(json.loads(config_path.read_text(encoding="utf-8")))
    assert "ghp_" not in serialized
    assert "gho_" not in serialized
    assert "/Users/" not in serialized
