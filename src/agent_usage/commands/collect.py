"""Pull local agent usage into the private ledger.

Each agent's collection window runs from its last checkpoint up to
``now``, or — on an agent's first-ever collection — exactly the
requested initial two-week backfill (2026-07-04 through 2026-07-18),
never further, so a first run never turns into an unrequested historic
scan. ``now`` must always be supplied by the caller rather than computed
here, the same explicit-time convention used throughout this project
(see e.g. ``render_dashboard``'s ``today``/``generated_at``), so
collection stays deterministic and testable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agent_usage.adapters import claude_code, codex, hermes
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.models import NormalizedUsageRecord, SourceStatus, SupportedAgent
from agent_usage.time_window import INITIAL_COLLECTION_WINDOW, TimeWindow

DEFAULT_HERMES_STATE_DB = Path.home() / ".hermes" / "state.db"
DEFAULT_CLAUDE_CODE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"

AdapterCollect = Callable[[Path, TimeWindow], list[NormalizedUsageRecord]]

ADAPTER_COLLECTORS: tuple[tuple[SupportedAgent, AdapterCollect], ...] = (
    (SupportedAgent.HERMES_AGENT, hermes.collect),
    (SupportedAgent.CLAUDE_CODE, claude_code.collect),
    (SupportedAgent.CODEX, codex.collect),
)

_STATUS_PRECEDENCE = (
    SourceStatus.AVAILABLE_WITH_ACTIVITY,
    SourceStatus.AVAILABLE_WITH_ZERO_ACTIVITY,
    SourceStatus.SOURCE_UNAVAILABLE,
)


@dataclass(frozen=True, slots=True)
class AgentCollectionResult:
    """The outcome of collecting one agent's source for one run.

    ``status`` is ``None`` when there was nothing new to collect this run
    (the agent's checkpoint had already caught up to ``now``) — distinct
    from the three ``SourceStatus`` values, which describe an
    actually-probed source.
    """

    agent: SupportedAgent
    status: SourceStatus | None
    records_observed: int
    records_inserted: int


def overall_source_status(records: list[NormalizedUsageRecord]) -> SourceStatus:
    """The most-informative status across a batch of collected records."""
    statuses = {record.source_status for record in records}
    for status in _STATUS_PRECEDENCE:
        if status in statuses:
            return status
    return SourceStatus.SOURCE_UNAVAILABLE


def collection_window(
    agent: SupportedAgent, repository: LedgerRepository, *, now: datetime
) -> TimeWindow | None:
    """The window to collect for one agent.

    Since the agent's last checkpoint, or exactly the requested initial
    backfill if it has never been collected before — never extended past
    the initial backfill's own end on a first run, per the "no
    unrequested historic scan" requirement. Returns None if there is
    nothing new to collect (the window would be empty).
    """
    checkpoint = repository.get_checkpoint(agent)
    if checkpoint is None:
        start = INITIAL_COLLECTION_WINDOW.start_utc
        end = min(INITIAL_COLLECTION_WINDOW.end_utc, now)
    else:
        start = checkpoint
        end = now

    if start >= end:
        return None
    return TimeWindow(start=start, end=end)


def source_paths_by_agent(
    *, hermes_db: Path, claude_projects_dir: Path, codex_sessions_dir: Path
) -> dict[SupportedAgent, Path]:
    """Map each supported agent to its local source path, in ADAPTER_COLLECTORS order."""
    return {
        SupportedAgent.HERMES_AGENT: hermes_db,
        SupportedAgent.CLAUDE_CODE: claude_projects_dir,
        SupportedAgent.CODEX: codex_sessions_dir,
    }


def collect_agent(
    agent: SupportedAgent,
    adapter_collect: AdapterCollect,
    source_path: Path,
    repository: LedgerRepository,
    *,
    now: datetime,
    dry_run: bool,
) -> AgentCollectionResult:
    """Collect one agent's new usage records and, unless dry-run, persist them."""
    window = collection_window(agent, repository, now=now)
    if window is None:
        return AgentCollectionResult(
            agent=agent, status=None, records_observed=0, records_inserted=0
        )

    records = adapter_collect(source_path, window)
    status = overall_source_status(records)

    inserted = 0
    if not dry_run:
        inserted = repository.insert_records(records)
        repository.set_checkpoint(agent, window.end_utc)

    return AgentCollectionResult(
        agent=agent, status=status, records_observed=len(records), records_inserted=inserted
    )


def collect_all(
    *,
    ledger_path: Path,
    hermes_db: Path,
    claude_projects_dir: Path,
    codex_sessions_dir: Path,
    now: datetime,
    dry_run: bool = False,
) -> list[AgentCollectionResult]:
    """Collect every supported agent's new usage into the local ledger."""
    source_paths = source_paths_by_agent(
        hermes_db=hermes_db,
        claude_projects_dir=claude_projects_dir,
        codex_sessions_dir=codex_sessions_dir,
    )
    repository = LedgerRepository.open(ledger_path)
    try:
        return [
            collect_agent(
                agent, adapter_collect, source_paths[agent], repository, now=now, dry_run=dry_run
            )
            for agent, adapter_collect in ADAPTER_COLLECTORS
        ]
    finally:
        repository.close()
