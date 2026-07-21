"""Render a local preview of the profile README dashboard from this device's own ledger data.

Stages this device's own sanitized daily records under ``output_dir`` (in
the same ``data/v1/devices/<device-id>/`` layout the public profile
repository uses) and renders the managed README section plus Plotly PNG chart
assets against them. Entirely local — never touches Git or the network.
Cross-device aggregation only happens once records are actually
published and picked up by the profile repository's own GitHub Action
(see ``templates/github-workflow.yml``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from agent_usage.aggregate import validate_and_partition
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.privacy import PrivacyPolicy
from agent_usage.public_data import stage_daily_records
from agent_usage.render.markdown import render_dashboard, update_readme

_ROLLING_CHART_RELATIVE_PATH = Path("assets/agent-usage/token-activity-14d.png")
_TOTAL_CHART_RELATIVE_PATH = Path("assets/agent-usage/token-activity-total.png")
_AGENT_SHARE_CHART_RELATIVE_PATH = Path("assets/agent-usage/agent-share.png")
_SKILLS_CHART_RELATIVE_PATH = Path("assets/agent-usage/skills.png")
_MCP_CHART_RELATIVE_PATH = Path("assets/agent-usage/mcp.png")


def _write_if_changed(path: Path, content: str | bytes) -> bool:
    if path.exists() and (
        path.read_bytes() if isinstance(content, bytes) else path.read_text(encoding="utf-8")
    ) == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return True


@dataclass(frozen=True, slots=True)
class RenderResult:
    device_id: str
    readme_path: Path
    changed: bool


def render(
    *,
    ledger_path: Path,
    output_dir: Path,
    privacy_policy: PrivacyPolicy = PrivacyPolicy(),
    today: date,
    generated_at: str,
    pie_top_n: int = 6,
) -> RenderResult:
    """Regenerate this device's local dashboard preview. Returns whether anything changed."""
    repository = LedgerRepository.open(ledger_path)
    try:
        device_id = repository.get_or_create_device_id()
        records = repository.list_records()
    finally:
        repository.close()

    device_data_dir = output_dir / "data" / "v1" / "devices" / device_id
    payloads = stage_daily_records(
        device_data_dir, device_id=device_id, records=records, privacy_policy=privacy_policy
    )

    partition = validate_and_partition(
        [(device_id, payload) for payload in payloads], today=today
    )

    rolling_chart_path = output_dir / _ROLLING_CHART_RELATIVE_PATH
    total_chart_path = output_dir / _TOTAL_CHART_RELATIVE_PATH
    agent_share_chart_path = output_dir / _AGENT_SHARE_CHART_RELATIVE_PATH
    skills_chart_path = output_dir / _SKILLS_CHART_RELATIVE_PATH
    mcp_chart_path = output_dir / _MCP_CHART_RELATIVE_PATH
    dashboard = render_dashboard(
        partition.valid_payloads,
        today=today,
        generated_at=generated_at,
        rolling_chart_path=_ROLLING_CHART_RELATIVE_PATH.as_posix(),
        total_chart_path=_TOTAL_CHART_RELATIVE_PATH.as_posix(),
        agent_share_chart_path=_AGENT_SHARE_CHART_RELATIVE_PATH.as_posix(),
        skills_chart_path=_SKILLS_CHART_RELATIVE_PATH.as_posix(),
        mcp_chart_path=_MCP_CHART_RELATIVE_PATH.as_posix(),
        pie_top_n=pie_top_n,
    )

    readme_path = output_dir / "README.md"
    existing_readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    updated_readme = update_readme(existing_readme, dashboard["markdown"])

    changed = _write_if_changed(readme_path, updated_readme)
    for chart_path, chart in (
        (rolling_chart_path, dashboard["charts"]["rolling"]),
        (total_chart_path, dashboard["charts"]["total"]),
        (agent_share_chart_path, dashboard["charts"]["agent_share"]),
        (skills_chart_path, dashboard["charts"]["skills"]),
        (mcp_chart_path, dashboard["charts"]["mcp"]),
    ):
        changed = _write_if_changed(chart_path, chart) or changed

    return RenderResult(device_id=device_id, readme_path=readme_path, changed=changed)
