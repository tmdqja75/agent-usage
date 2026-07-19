"""Build the profile README dashboard from public per-device aggregates.

Run inside the profile repository's GitHub Action (see
``templates/github-workflow.yml``): reads every device's daily JSON
records under ``data/v1/devices/``, validates them defensively — they may
originate from any device pushing to the shared public repo, so this is
not just a re-check of trusted local output — and regenerates the managed
README section plus its Plotly-generated PNG chart assets. A malformed or invalid record
is skipped and reported as a diagnostic on stderr rather than aborting
the whole build, so one bad device partition never blocks everyone
else's dashboard. Diagnostics only ever include the device id, date, and
rejection reason already carried by ``ValidationIssue`` — never record
content.

Not part of the installable ``agent_usage`` package: it is meant to be
checked out from this repo and invoked directly in the profile repo's CI,
per the workflow template.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from agent_usage.aggregate import validate_and_partition
from agent_usage.render.markdown import render_dashboard, update_readme

DEFAULT_DATA_DIR = Path("data/v1/devices")
DEFAULT_README = Path("README.md")
DEFAULT_ROLLING_CHART = Path("assets/agent-usage/token-activity-14d.png")
DEFAULT_TOTAL_CHART = Path("assets/agent-usage/token-activity-total.png")
DEFAULT_SKILLS_CHART = Path("assets/agent-usage/skills.png")
DEFAULT_MCP_CHART = Path("assets/agent-usage/mcp.png")


def _load_entries(data_dir: Path) -> list[tuple[str, object]]:
    """Load every ``<device_id>/<date>.json`` file under ``data_dir``.

    A file that fails to read or parse becomes an entry with payload
    ``None``, so ``validate_and_partition`` rejects it with a diagnostic
    like any other malformed record instead of the whole build crashing.
    """
    entries: list[tuple[str, object]] = []
    if not data_dir.is_dir():
        return entries
    for device_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        device_id = device_dir.name
        for record_path in sorted(device_dir.glob("*.json")):
            try:
                payload = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            entries.append((device_id, payload))
    return entries


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


def _readme_relative_path(path: Path, *, readme_path: Path) -> str:
    """Return a README image path relative to the README when possible."""
    try:
        return path.relative_to(readme_path.parent).as_posix()
    except ValueError:
        return path.as_posix()


def build(
    *,
    data_dir: Path,
    readme_path: Path,
    rolling_chart_path: Path,
    total_chart_path: Path | None = None,
    skills_chart_path: Path | None = None,
    mcp_chart_path: Path | None = None,
    lifetime_chart_path: Path | None = None,
    today: date,
    generated_at: str,
) -> bool:
    """Regenerate the README and chart assets. Returns True if anything changed."""
    if total_chart_path is None:
        if lifetime_chart_path is None:
            raise ValueError("total_chart_path is required")
        total_chart_path = lifetime_chart_path.with_suffix(".png")
    chart_dir = total_chart_path.parent
    skills_chart_path = skills_chart_path or chart_dir / DEFAULT_SKILLS_CHART.name
    mcp_chart_path = mcp_chart_path or chart_dir / DEFAULT_MCP_CHART.name

    entries = _load_entries(data_dir)
    partition = validate_and_partition(entries, today=today)
    for issue in partition.issues:
        print(
            f"agent-usage: skipping invalid record "
            f"device={issue.device_id} date={issue.date} reason={issue.reason}",
            file=sys.stderr,
        )

    dashboard = render_dashboard(
        partition.valid_payloads,
        today=today,
        generated_at=generated_at,
        rolling_chart_path=_readme_relative_path(rolling_chart_path, readme_path=readme_path),
        total_chart_path=_readme_relative_path(total_chart_path, readme_path=readme_path),
        skills_chart_path=_readme_relative_path(skills_chart_path, readme_path=readme_path),
        mcp_chart_path=_readme_relative_path(mcp_chart_path, readme_path=readme_path),
    )

    existing_readme = (
        readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    )
    updated_readme = update_readme(existing_readme, dashboard["markdown"])

    changed = _write_if_changed(readme_path, updated_readme)
    for chart_path, chart in (
        (rolling_chart_path, dashboard["charts"]["rolling"]),
        (total_chart_path, dashboard["charts"]["total"]),
        (skills_chart_path, dashboard["charts"]["skills"]),
        (mcp_chart_path, dashboard["charts"]["mcp"]),
    ):
        changed = _write_if_changed(chart_path, chart) or changed
    return changed


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--rolling-chart", type=Path, default=DEFAULT_ROLLING_CHART)
    parser.add_argument("--total-chart", type=Path, default=DEFAULT_TOTAL_CHART)
    parser.add_argument("--lifetime-chart", type=Path, dest="lifetime_chart", help=argparse.SUPPRESS)
    parser.add_argument("--skills-chart", type=Path, default=DEFAULT_SKILLS_CHART)
    parser.add_argument("--mcp-chart", type=Path, default=DEFAULT_MCP_CHART)
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="Override today's date (UTC); defaults to the current date.",
    )
    parser.add_argument(
        "--generated-at",
        type=str,
        default=None,
        help="Override the 'last updated' timestamp shown in the dashboard.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    now = datetime.now(timezone.utc)
    today = args.today or now.date()
    generated_at = args.generated_at or now.strftime("%Y-%m-%d %H:%M UTC")
    default_chart_dir = args.readme.parent / "assets" / "agent-usage"
    rolling_chart_path = (
        default_chart_dir / DEFAULT_ROLLING_CHART.name
        if args.rolling_chart == DEFAULT_ROLLING_CHART
        else args.rolling_chart
    )
    skills_chart_path = (
        default_chart_dir / DEFAULT_SKILLS_CHART.name
        if args.skills_chart == DEFAULT_SKILLS_CHART
        else args.skills_chart
    )
    mcp_chart_path = (
        default_chart_dir / DEFAULT_MCP_CHART.name
        if args.mcp_chart == DEFAULT_MCP_CHART
        else args.mcp_chart
    )
    total_chart_path = (
        default_chart_dir / DEFAULT_TOTAL_CHART.name
        if args.total_chart == DEFAULT_TOTAL_CHART
        else args.total_chart
    )

    changed = build(
        data_dir=args.data_dir,
        readme_path=args.readme,
        rolling_chart_path=rolling_chart_path,
        total_chart_path=total_chart_path if args.lifetime_chart is None else None,
        skills_chart_path=skills_chart_path,
        mcp_chart_path=mcp_chart_path,
        lifetime_chart_path=args.lifetime_chart,
        today=today,
        generated_at=generated_at,
    )
    print("agent-usage: dashboard changed" if changed else "agent-usage: dashboard unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
