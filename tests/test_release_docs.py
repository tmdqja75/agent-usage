"""Contract tests for Task 16 release guidance and collector CI."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _read_doc(name: str) -> str:
    return (DOCS_DIR / name).read_text(encoding="utf-8")


def test_privacy_guide_documents_the_public_boundary_and_statuses() -> None:
    text = _read_doc("privacy.md")

    for required in (
        "read-only",
        "source_unavailable",
        "available_with_zero_activity",
        "prompts",
        "transcripts",
        "raw session IDs",
        "data/v1/devices/<opaque-device-id>/<YYYY-MM-DD>.json",
    ):
        assert required in text


def test_multi_device_guide_documents_safe_device_partitions_and_profile_workflow() -> None:
    text = _read_doc("multi-device.md")

    for required in (
        "opaque device ID",
        "data/v1/devices/<opaque-device-id>/<YYYY-MM-DD>.json",
        "GitHub Actions",
        "agent-usage init --repo OWNER/PROFILE-REPO",
        "agent-usage collect",
        "agent-usage publish",
    ):
        assert required in text


def test_troubleshooting_documents_status_and_accounting_semantics() -> None:
    text = _read_doc("troubleshooting.md")

    for required in (
        "source_unavailable",
        "available_with_zero_activity",
        "Claude Code",
        "do not estimate",
        "Codex",
        "monotonic",
        "gh auth status",
        "launchd",
        "2026-07-04",
        "2026-07-18",
    ):
        assert required in text


def test_collector_ci_runs_the_release_verification_commands() -> None:
    text = CI_PATH.read_text(encoding="utf-8")

    for required in (
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "astral-sh/setup-uv@v8",
        "uv sync --dev --locked",
        'git config --global user.name "agent-usage CI"',
        'git config --global user.email "agent-usage-ci@users.noreply.github.com"',
        "uv run pytest -q",
        "uv run ruff check .",
        "uv build",
        "uv run agent-usage --help",
    ):
        assert required in text


def test_collector_ci_runs_for_pushes_and_pull_requests() -> None:
    text = CI_PATH.read_text(encoding="utf-8")

    assert "push:" in text
    assert "pull_request:" in text
    assert "main" in text


def test_readme_links_to_the_release_guides() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for guide in ("docs/privacy.md", "docs/multi-device.md", "docs/troubleshooting.md"):
        assert guide in text
    assert "session content, raw identifiers" in text
