"""Local, read-only diagnostics: config, ledger, and per-agent source health.

Probes each adapter's current collection window exactly like ``collect``
would, but never writes ledger events or moves checkpoints, so running
``doctor`` never disturbs a future ``collect`` run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agent_usage.commands.collect import (
    ADAPTER_COLLECTORS,
    collection_window,
    overall_source_status,
    source_paths_by_agent,
)
from agent_usage.config import load_config, resolve_initial_collection_start
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.models import SourceStatus, SupportedAgent


@dataclass(frozen=True, slots=True)
class SourceDiagnostic:
    """One agent's probed source status, or None if already caught up."""

    agent: SupportedAgent
    status: SourceStatus | None


@dataclass(frozen=True, slots=True)
class DoctorReport:
    device_id: str
    repo_target: str | None
    display_timezone: str
    initial_collection_start: str | None
    bar_chart_threshold_days: int
    sources: tuple[SourceDiagnostic, ...]


def run_doctor(
    *,
    config_path: Path,
    ledger_path: Path,
    hermes_db: Path,
    claude_projects_dir: Path,
    codex_sessions_dir: Path,
    now: datetime,
) -> DoctorReport:
    """Summarize local configuration and probe each agent source's current status."""
    config = load_config(config_path)
    configured_start = resolve_initial_collection_start(config.initial_collection_start)
    source_paths = source_paths_by_agent(
        hermes_db=hermes_db,
        claude_projects_dir=claude_projects_dir,
        codex_sessions_dir=codex_sessions_dir,
    )

    repository = LedgerRepository.open(ledger_path)
    try:
        device_id = repository.get_or_create_device_id()
        sources = []
        for agent, adapter_collect in ADAPTER_COLLECTORS:
            window = collection_window(
                agent, repository, now=now, configured_start=configured_start
            )
            if window is None:
                sources.append(SourceDiagnostic(agent=agent, status=None))
                continue
            records = adapter_collect(source_paths[agent], window)
            sources.append(SourceDiagnostic(agent=agent, status=overall_source_status(records)))
    finally:
        repository.close()

    return DoctorReport(
        device_id=device_id,
        repo_target=config.repo_target,
        display_timezone=config.display_timezone,
        initial_collection_start=config.initial_collection_start,
        bar_chart_threshold_days=config.bar_chart_threshold_days,
        sources=tuple(sources),
    )
