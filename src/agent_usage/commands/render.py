"""Render a local preview of the profile README dashboard from this device's own ledger data.

Stages this device's own sanitized daily records under ``output_dir`` (in
the same ``data/v1/devices/<device-id>/`` layout the public profile
repository uses) and renders the managed README section plus SVG chart
assets against them. Entirely local — never touches Git or the network.
Cross-device aggregation only happens once records are actually
published and picked up by the profile repository's own GitHub Action
(see ``templates/github-workflow.yml``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timezone
from pathlib import Path

from agent_usage.aggregate import validate_and_partition
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.privacy import PrivacyPolicy
from agent_usage.public_data import build_daily_record, write_daily_record
from agent_usage.render.markdown import render_dashboard, update_readme

UTC = timezone.utc

_ROLLING_CHART_RELATIVE_PATH = Path("assets/agent-usage/rolling-14d.svg")
_LIFETIME_CHART_RELATIVE_PATH = Path("assets/agent-usage/lifetime.svg")


def _write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
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
) -> RenderResult:
    """Regenerate this device's local dashboard preview. Returns whether anything changed."""
    repository = LedgerRepository.open(ledger_path)
    try:
        device_id = repository.get_or_create_device_id()
        records = repository.list_records()
    finally:
        repository.close()

    days = sorted({record.occurred_at.astimezone(UTC).date() for record in records})
    device_data_dir = output_dir / "data" / "v1" / "devices" / device_id

    payloads = []
    for day in days:
        payload = build_daily_record(
            device_id=device_id, day=day, records=records, privacy_policy=privacy_policy
        )
        write_daily_record(device_data_dir / f"{day.isoformat()}.json", payload)
        payloads.append(payload)

    partition = validate_and_partition(
        [(device_id, payload) for payload in payloads], today=today
    )

    rolling_chart_path = output_dir / _ROLLING_CHART_RELATIVE_PATH
    lifetime_chart_path = output_dir / _LIFETIME_CHART_RELATIVE_PATH
    dashboard = render_dashboard(
        partition.valid_payloads,
        today=today,
        generated_at=generated_at,
        rolling_chart_path=_ROLLING_CHART_RELATIVE_PATH.as_posix(),
        lifetime_chart_path=_LIFETIME_CHART_RELATIVE_PATH.as_posix(),
    )

    readme_path = output_dir / "README.md"
    existing_readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    updated_readme = update_readme(existing_readme, dashboard["markdown"])

    changed = _write_if_changed(readme_path, updated_readme)
    changed = _write_if_changed(rolling_chart_path, dashboard["rolling_svg"]) or changed
    changed = _write_if_changed(lifetime_chart_path, dashboard["lifetime_svg"]) or changed

    return RenderResult(device_id=device_id, readme_path=readme_path, changed=changed)
