"""Render a local preview of the profile README dashboard from this device's own ledger data.

Stages this device's own sanitized daily records under ``output_dir`` (in
the same ``data/v1/devices/<device-id>/`` layout the public profile
repository uses) and updates the managed README section to reference the
dashboard screenshot. Entirely local — never touches Git or the network.
Cross-device aggregation only happens once records are actually
published and picked up by the profile repository's own GitHub Action
(see ``templates/github-workflow.yml``).

Note: The dashboard screenshot must be generated separately by calling
``agent_usage.dashboard.export.export_dashboard_png``, which requires the
full UI build and Playwright setup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from agent_usage.aggregate import validate_and_partition
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.privacy import PrivacyPolicy
from agent_usage.public_data import stage_daily_records
from agent_usage.render.markdown import DASHBOARD_IMAGE_PATH, render_dashboard_markdown, update_readme

_DASHBOARD_RELATIVE_PATH = Path(DASHBOARD_IMAGE_PATH)


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
    """Regenerate this device's local README with the managed dashboard section.

    Returns whether the README changed. The dashboard screenshot must be generated
    separately using ``agent_usage.dashboard.export.export_dashboard_png``.
    """
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

    # Render the markdown section (screenshot must be generated separately)
    markdown = render_dashboard_markdown(image_path=_DASHBOARD_RELATIVE_PATH.as_posix())

    readme_path = output_dir / "README.md"
    existing_readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    updated_readme = update_readme(existing_readme, markdown)

    changed = _write_if_changed(readme_path, updated_readme)

    return RenderResult(device_id=device_id, readme_path=readme_path, changed=changed)
