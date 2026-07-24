"""Local, network-free setup: record the profile repo target and ensure a device id exists.

Never touches GitHub or the network — that only happens in the
``publish`` command, gated behind its own ``gh auth status`` check.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tomax.config import AppConfig, get_or_create_device_id, load_config, save_config


def init(repo: str, *, config_path: Path, ledger_path: Path) -> AppConfig:
    """Set the profile repo target in local config, creating the device id if needed."""
    config = replace(load_config(config_path), repo_target=repo)
    save_config(config_path, config)
    get_or_create_device_id(ledger_path)
    return config
