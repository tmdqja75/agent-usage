"""`agent-usage dashboard`: build the payload and serve the interactive localhost dashboard."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agent_usage.config import load_config
from agent_usage.dashboard.payload import build_payload
from agent_usage.dashboard.remote import NoRepoTargetError
from agent_usage.dashboard.server import serve
from agent_usage.dashboard.ui_build import UIBuildError, ensure_build
from agent_usage.privacy import PrivacyPolicy

# The React UI source lives at the repo root under dashboard-ui/.
# commands/dashboard.py -> commands -> agent_usage -> src -> <repo root>.
UI_DIR = Path(__file__).resolve().parents[3] / "dashboard-ui"


class DashboardError(Exception):
    """A user-facing dashboard failure (surfaced by the CLI as a clean message)."""


def run(
    *,
    ledger_path: Path,
    config_path: Path,
    all_devices: bool,
    port: int,
    open_browser: bool,
    pie_top_n: int,
    lang: str,
    ui_dir: Path,
    force_build: bool,
    today: date,
    tmp_stage_dir: Path,
) -> None:
    """Build the payload, build the UI on demand, and serve until interrupted."""
    config = load_config(config_path)
    try:
        data = build_payload(
            ledger_path=ledger_path,
            all_devices=all_devices,
            repo_target=config.repo_target,
            privacy_policy=PrivacyPolicy.from_config(config),
            today=today,
            pie_top_n=pie_top_n,
            bar_chart_threshold_days=config.bar_chart_threshold_days,
            tmp_stage_dir=tmp_stage_dir,
        )
    except NoRepoTargetError as error:
        raise DashboardError(str(error)) from error

    if not ui_dir.is_dir():
        raise DashboardError(
            f"dashboard UI source not found at {ui_dir} — run from a repository checkout"
        )
    try:
        dist_dir = ensure_build(ui_dir, force=force_build)
    except UIBuildError as error:
        raise DashboardError(str(error)) from error

    serve(data, dist_dir=dist_dir, port=port, open_browser=open_browser, lang=lang)
