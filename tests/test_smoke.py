"""Smoke tests for the installed project command."""

from __future__ import annotations

import subprocess


def test_agent_usage_help() -> None:
    """The installed command exposes a help screen."""
    result = subprocess.run(
        ["agent-usage", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
