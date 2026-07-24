# Configurable Collection Start Date Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users configure how far back the first-ever collection for each agent reaches — either a custom start date or unbounded ("ALL" history) — and, when they widen that window after already collecting data, backfill the gap between the new start date and their earliest existing record without disturbing the forward checkpoint.

**Architecture:** A new `AppConfig.initial_collection_start` field (`None` | `"ALL"` | `"YYYY-MM-DD"`) resolves to a concrete UTC `datetime` in `config.py`. `collect_agent` gains a second, independent "backfill" window alongside its existing forward "checkpoint → now" window, computed by comparing the configured start to the agent's earliest stored record. A new `tomax config start-date` CLI command writes the setting; `collect` and `doctor` both resolve and use it, so manual and scheduled runs behave identically.

**Tech Stack:** Python, typer (CLI), sqlite3, pytest.

## Global Constraints

- Checkpoint (`repository.get_checkpoint`/`set_checkpoint`) keeps its current meaning — a forward-only pointer — and is never reset by a start-date config change.
- `"ALL"` resolves to `EPOCH_START = datetime(1970, 1, 1, tzinfo=UTC)`.
- Default (`initial_collection_start is None`) keeps today's start date, 2026-07-04, but the first-run window no longer has a fixed end — it always runs `start → now`.
- The backfill window is idempotent by construction: once an agent's earliest record reaches the configured start, the comparison stops producing a window on later runs. No new persisted state for it.

---

### Task 1: `time_window.py` — drop the fixed backfill end, add `EPOCH_START`

**Files:**
- Modify: `src/tomax/time_window.py:66-69`
- Test: `tests/test_time_window.py`

**Interfaces:**
- Produces: `DEFAULT_INITIAL_START: datetime` (replaces `INITIAL_COLLECTION_WINDOW`), `EPOCH_START: datetime`.

- [ ] **Step 1: Update the test file for the new constants**

Replace the two tests that assert a fixed 14-day backfill window with tests for the new plain-datetime constants. Edit `tests/test_time_window.py`:

```python
"""Tests for deterministic UTC collection windows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tomax.time_window import DEFAULT_INITIAL_START, EPOCH_START, TimeWindow, normalize_utc


UTC = timezone.utc


def test_default_initial_start_is_the_2026_07_04_backfill_date() -> None:
    assert DEFAULT_INITIAL_START == datetime(2026, 7, 4, 0, 0, tzinfo=UTC)


def test_epoch_start_is_unix_epoch_for_unbounded_all_history_backfill() -> None:
    assert EPOCH_START == datetime(1970, 1, 1, tzinfo=UTC)


def test_window_normalizes_offset_inputs_before_membership_check() -> None:
    window = TimeWindow(
        start=datetime(2026, 7, 4, tzinfo=UTC),
        end=datetime(2026, 7, 18, tzinfo=UTC),
    )
    assert window.contains(datetime(2026, 7, 4, 9, 0, tzinfo=timezone(timedelta(hours=9))))
```

Keep every other existing test in the file unchanged (the `TimeWindow`-construction tests, `normalize_utc` tests, etc. — only the two tests that referenced `INITIAL_COLLECTION_WINDOW` are replaced above). Search the file for `INITIAL_COLLECTION_WINDOW` and remove any other reference.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_time_window.py -v`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_INITIAL_START'`

- [ ] **Step 3: Replace the constant in `time_window.py`**

At the bottom of `src/tomax/time_window.py`, replace:

```python
INITIAL_COLLECTION_WINDOW = TimeWindow(
    start=datetime(2026, 7, 4, 0, 0, tzinfo=UTC),
    end=datetime(2026, 7, 18, 0, 0, tzinfo=UTC),
)
```

with:

```python
DEFAULT_INITIAL_START = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
"""Default first-run collection start when no config override is set."""

EPOCH_START = datetime(1970, 1, 1, 0, 0, tzinfo=UTC)
"""Sentinel start used to request unbounded ('ALL') history backfill."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_time_window.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tomax/time_window.py tests/test_time_window.py
git commit -m "feat(time-window): replace fixed initial backfill window with configurable start constants"
```

---

### Task 2: `LedgerRepository.get_earliest_record_at`

**Files:**
- Modify: `src/tomax/ledger/repository.py`
- Test: `tests/ledger/test_repository.py`

**Interfaces:**
- Consumes: existing `_record` test helper in `tests/ledger/test_repository.py` (agent, occurred_at, fingerprint, ...).
- Produces: `LedgerRepository.get_earliest_record_at(agent: SupportedAgent) -> datetime | None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/ledger/test_repository.py` (near the other checkpoint tests):

```python
def test_get_earliest_record_at_returns_none_when_agent_has_no_records(tmp_path) -> None:
    repo = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        assert repo.get_earliest_record_at(SupportedAgent.CLAUDE_CODE) is None
    finally:
        repo.close()


def test_get_earliest_record_at_returns_the_minimum_occurred_at_for_that_agent(tmp_path) -> None:
    repo = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        repo.insert_records(
            [
                _record("a", occurred_at=datetime(2026, 7, 10, tzinfo=UTC)),
                _record("b", occurred_at=datetime(2026, 7, 5, tzinfo=UTC)),
                _record("c", occurred_at=datetime(2026, 7, 20, tzinfo=UTC)),
                _record(
                    "d",
                    agent=SupportedAgent.CODEX,
                    occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
                ),
            ]
        )
        earliest = repo.get_earliest_record_at(SupportedAgent.CLAUDE_CODE)
    finally:
        repo.close()

    assert earliest == datetime(2026, 7, 5, tzinfo=UTC)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ledger/test_repository.py -k earliest_record -v`
Expected: FAIL with `AttributeError: 'LedgerRepository' object has no attribute 'get_earliest_record_at'`

- [ ] **Step 3: Implement `get_earliest_record_at`**

Add to `src/tomax/ledger/repository.py`, directly below `get_checkpoint`:

```python
    def get_earliest_record_at(self, agent: SupportedAgent) -> datetime | None:
        """Return the earliest stored record's timestamp for an agent, or None if it has none."""
        row = self._connection.execute(
            "SELECT MIN(occurred_at) AS earliest FROM events WHERE agent = ?",
            (agent.value,),
        ).fetchone()
        if row is None or row["earliest"] is None:
            return None
        return normalize_utc(datetime.fromisoformat(row["earliest"]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ledger/test_repository.py -k earliest_record -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tomax/ledger/repository.py tests/ledger/test_repository.py
git commit -m "feat(ledger): add get_earliest_record_at for per-agent backfill gap detection"
```

---

### Task 3: `AppConfig.initial_collection_start` + resolver

**Files:**
- Modify: `src/tomax/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `DEFAULT_INITIAL_START`, `EPOCH_START` from `tomax.time_window` (Task 1).
- Produces: `AppConfig.initial_collection_start: str | None` field; `resolve_initial_collection_start(value: str | None) -> datetime`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
from datetime import datetime, timezone

from tomax.config import resolve_initial_collection_start
from tomax.time_window import DEFAULT_INITIAL_START, EPOCH_START

UTC = timezone.utc


def test_default_config_has_no_initial_collection_start_override() -> None:
    config = AppConfig()

    assert config.initial_collection_start is None


@pytest.mark.parametrize("bad_value", ["", "not-a-date", "2026/07/04", "2026-13-40"])
def test_config_rejects_malformed_initial_collection_start(bad_value: str) -> None:
    with pytest.raises(ValueError, match="initial_collection_start"):
        AppConfig(initial_collection_start=bad_value)


def test_config_accepts_all_and_a_well_formed_iso_date_for_initial_collection_start() -> None:
    assert AppConfig(initial_collection_start="ALL").initial_collection_start == "ALL"
    assert (
        AppConfig(initial_collection_start="2026-01-01").initial_collection_start
        == "2026-01-01"
    )


def test_resolve_initial_collection_start_none_uses_the_default() -> None:
    assert resolve_initial_collection_start(None) == DEFAULT_INITIAL_START


def test_resolve_initial_collection_start_all_is_unbounded() -> None:
    assert resolve_initial_collection_start("ALL") == EPOCH_START


def test_resolve_initial_collection_start_parses_a_custom_iso_date() -> None:
    assert resolve_initial_collection_start("2026-01-01") == datetime(2026, 1, 1, tzinfo=UTC)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `TypeError: AppConfig.__init__() got an unexpected keyword argument 'initial_collection_start'`

- [ ] **Step 3: Implement the field, validation, and resolver**

In `src/tomax/config.py`, add imports at the top:

```python
from datetime import datetime

from tomax.time_window import DEFAULT_INITIAL_START, EPOCH_START, UTC
```

(`UTC` doesn't currently exist as a public name in `time_window.py` — check Task 1's file: it's `UTC = timezone.utc` at module level, already public. Import it directly.)

Add a module-level validator near the other regex constants:

```python
def _validate_initial_collection_start(value: str | None) -> None:
    if value is None or value == "ALL":
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(
            "initial_collection_start must be None, 'ALL', or an ISO date (YYYY-MM-DD)"
        ) from error
```

Add the field to `AppConfig` (after `display_timezone`, before `schedule_enabled`):

```python
    initial_collection_start: str | None = None
```

Call the validator in `__post_init__`, after the `display_timezone` check:

```python
        _validate_initial_collection_start(self.initial_collection_start)
```

Update `to_dict`/`from_dict` — `to_dict` needs no change (plain `asdict` already includes it); `from_dict` needs:

```python
            initial_collection_start=data.get("initial_collection_start"),
```

(add this line inside the `cls(...)` call, alongside the other `data.get(...)` lines).

Add the resolver function at module scope, near `load_config`/`save_config`:

```python
def resolve_initial_collection_start(value: str | None) -> datetime:
    """Resolve a config's ``initial_collection_start`` to a concrete UTC datetime."""
    if value is None:
        return DEFAULT_INITIAL_START
    if value == "ALL":
        return EPOCH_START
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tomax/config.py tests/test_config.py
git commit -m "feat(config): add initial_collection_start setting and resolver"
```

---

### Task 4: `collect.py` — parameterized start + backfill gap window

**Files:**
- Modify: `src/tomax/commands/collect.py`
- Test: `tests/commands/test_collect.py`

**Interfaces:**
- Consumes: `DEFAULT_INITIAL_START` (Task 1), `LedgerRepository.get_earliest_record_at` (Task 2).
- Produces: `collection_window(agent, repository, *, now, configured_start=DEFAULT_INITIAL_START) -> TimeWindow | None` (forward window only, signature gains `configured_start`); `backfill_window(agent, repository, *, configured_start) -> TimeWindow | None`; `collect_agent(..., configured_start=DEFAULT_INITIAL_START)`; `collect_all(..., configured_start=DEFAULT_INITIAL_START)`. All existing fields on `AgentCollectionResult` unchanged.

- [ ] **Step 1: Update existing tests for the new signature and behavior**

In `tests/commands/test_collect.py`:

1. Change the import line:

```python
from tomax.time_window import DEFAULT_INITIAL_START
```

2. Replace `test_collection_window_uses_the_initial_backfill_when_no_checkpoint`:

```python
def test_collection_window_uses_the_default_initial_start_when_no_checkpoint(tmp_path) -> None:
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        window = collection_window(SupportedAgent.CLAUDE_CODE, repository, now=NOW)
    finally:
        repository.close()

    assert window is not None
    assert window.start_utc == DEFAULT_INITIAL_START
    assert window.end_utc == NOW
```

3. Delete `test_collection_window_never_extends_the_initial_backfill_past_its_own_end` entirely — the fixed-end cap it tested no longer exists (first-run windows now always run to `now`).

4. Add a new test after it, confirming a custom `configured_start` is honored and a first run always extends to `now`:

```python
def test_collection_window_first_run_always_extends_to_now_with_no_fixed_cap(tmp_path) -> None:
    far_future = datetime(2027, 1, 1, tzinfo=UTC)
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        window = collection_window(SupportedAgent.CLAUDE_CODE, repository, now=far_future)
    finally:
        repository.close()

    assert window is not None
    assert window.start_utc == DEFAULT_INITIAL_START
    assert window.end_utc == far_future


def test_collection_window_honors_a_custom_configured_start(tmp_path) -> None:
    custom_start = datetime(2026, 1, 1, tzinfo=UTC)
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        window = collection_window(
            SupportedAgent.CLAUDE_CODE, repository, now=NOW, configured_start=custom_start
        )
    finally:
        repository.close()

    assert window is not None
    assert window.start_utc == custom_start
    assert window.end_utc == NOW
```

5. `test_collection_window_continues_from_the_checkpoint_after_the_first_run` and `test_collection_window_is_none_when_already_caught_up` need no changes — `configured_start` only matters when there's no checkpoint.

6. Add backfill-window and `collect_agent` gap-fill tests, near the `collect_all` tests:

```python
# --- backfill_window ------------------------------------------------------


def test_backfill_window_is_none_when_agent_has_no_existing_records(tmp_path) -> None:
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        window = backfill_window(
            SupportedAgent.CLAUDE_CODE, repository, configured_start=DEFAULT_INITIAL_START
        )
    finally:
        repository.close()

    assert window is None


def test_backfill_window_is_none_when_configured_start_is_not_earlier_than_earliest_record(
    tmp_path,
) -> None:
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        repository.insert_records(
            [
                NormalizedUsageRecord(
                    agent=SupportedAgent.CLAUDE_CODE,
                    occurred_at=datetime(2026, 7, 10, tzinfo=UTC),
                    fingerprint="a",
                    tokens=TokenUsage(input_tokens=1),
                    source_status=SourceStatus.AVAILABLE_WITH_ACTIVITY,
                )
            ]
        )
        window = backfill_window(
            SupportedAgent.CLAUDE_CODE,
            repository,
            configured_start=datetime(2026, 7, 10, tzinfo=UTC),
        )
    finally:
        repository.close()

    assert window is None


def test_backfill_window_covers_the_gap_before_the_earliest_existing_record(tmp_path) -> None:
    repository = LedgerRepository.open(tmp_path / "ledger.sqlite3")
    try:
        repository.insert_records(
            [
                NormalizedUsageRecord(
                    agent=SupportedAgent.CLAUDE_CODE,
                    occurred_at=datetime(2026, 7, 10, tzinfo=UTC),
                    fingerprint="a",
                    tokens=TokenUsage(input_tokens=1),
                    source_status=SourceStatus.AVAILABLE_WITH_ACTIVITY,
                )
            ]
        )
        window = backfill_window(
            SupportedAgent.CLAUDE_CODE,
            repository,
            configured_start=datetime(2026, 1, 1, tzinfo=UTC),
        )
    finally:
        repository.close()

    assert window is not None
    assert window.start_utc == datetime(2026, 1, 1, tzinfo=UTC)
    assert window.end_utc == datetime(2026, 7, 10, tzinfo=UTC)


# --- collect_agent: backfill gap-fill --------------------------------------


def test_collect_agent_backfills_the_gap_without_disturbing_the_forward_checkpoint(
    tmp_path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite3"
    repository = LedgerRepository.open(ledger_path)
    try:
        checkpoint = datetime(2026, 7, 15, tzinfo=UTC)
        repository.set_checkpoint(SupportedAgent.CLAUDE_CODE, checkpoint)
        repository.insert_records(
            [
                NormalizedUsageRecord(
                    agent=SupportedAgent.CLAUDE_CODE,
                    occurred_at=datetime(2026, 7, 10, tzinfo=UTC),
                    fingerprint="existing",
                    tokens=TokenUsage(input_tokens=1),
                    source_status=SourceStatus.AVAILABLE_WITH_ACTIVITY,
                )
            ]
        )

        seen_windows = []

        def fake_adapter_collect(source_path, window):
            seen_windows.append((window.start_utc, window.end_utc))
            return [
                NormalizedUsageRecord(
                    agent=SupportedAgent.CLAUDE_CODE,
                    occurred_at=window.start_utc,
                    fingerprint=f"backfilled-{window.start_utc.isoformat()}",
                    tokens=TokenUsage(input_tokens=1),
                    source_status=SourceStatus.AVAILABLE_WITH_ACTIVITY,
                )
            ]

        result = collect_agent(
            SupportedAgent.CLAUDE_CODE,
            fake_adapter_collect,
            tmp_path / "unused-source",
            repository,
            now=NOW,
            dry_run=False,
            configured_start=datetime(2026, 1, 1, tzinfo=UTC),
        )

        final_checkpoint = repository.get_checkpoint(SupportedAgent.CLAUDE_CODE)
        stored = repository.list_records(SupportedAgent.CLAUDE_CODE)
    finally:
        repository.close()

    assert sorted(seen_windows) == [
        (checkpoint, NOW),
        (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 7, 10, tzinfo=UTC)),
    ]
    assert final_checkpoint == NOW
    assert result.records_observed == 2
    assert result.records_inserted == 2
    assert len(stored) == 3
```

Also add `backfill_window` and `collect_agent` to the imports at the top of the test file:

```python
from tomax.commands.collect import (
    AgentCollectionResult,
    backfill_window,
    collect_agent,
    collect_all,
    collection_window,
    overall_source_status,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/commands/test_collect.py -v`
Expected: FAIL — `ImportError: cannot import name 'backfill_window'` and `TypeError` on `configured_start` kwargs.

- [ ] **Step 3: Implement in `collect.py`**

Update the import line:

```python
from tomax.time_window import DEFAULT_INITIAL_START, TimeWindow
```

Update `collection_window`:

```python
def collection_window(
    agent: SupportedAgent,
    repository: LedgerRepository,
    *,
    now: datetime,
    configured_start: datetime = DEFAULT_INITIAL_START,
) -> TimeWindow | None:
    """The forward window to collect for one agent.

    Since the agent's last checkpoint, or from ``configured_start`` through
    ``now`` on an agent's first-ever collection — no fixed cap, so a widened
    ``configured_start`` always reaches all the way to ``now`` on a first
    run. Returns None if there is nothing new to collect (the window would
    be empty).
    """
    checkpoint = repository.get_checkpoint(agent)
    start = checkpoint if checkpoint is not None else configured_start
    end = now

    if start >= end:
        return None
    return TimeWindow(start=start, end=end)
```

Add `backfill_window` directly below it:

```python
def backfill_window(
    agent: SupportedAgent, repository: LedgerRepository, *, configured_start: datetime
) -> TimeWindow | None:
    """The gap window to backfill when ``configured_start`` predates existing records.

    None if the agent has no records yet (nothing to backfill against — the
    forward window from ``collection_window`` already covers a first run),
    or if ``configured_start`` is not earlier than the earliest existing
    record (the gap is already closed).
    """
    earliest = repository.get_earliest_record_at(agent)
    if earliest is None or configured_start >= earliest:
        return None
    return TimeWindow(start=configured_start, end=earliest)
```

Update `collect_agent`:

```python
def collect_agent(
    agent: SupportedAgent,
    adapter_collect: AdapterCollect,
    source_path: Path,
    repository: LedgerRepository,
    *,
    now: datetime,
    dry_run: bool,
    configured_start: datetime = DEFAULT_INITIAL_START,
) -> AgentCollectionResult:
    """Collect one agent's new usage records — forward and any backfill gap — and persist them."""
    forward = collection_window(agent, repository, now=now, configured_start=configured_start)
    backfill = backfill_window(agent, repository, configured_start=configured_start)

    if forward is None and backfill is None:
        return AgentCollectionResult(
            agent=agent, status=None, records_observed=0, records_inserted=0
        )

    records: list[NormalizedUsageRecord] = []
    if forward is not None:
        records.extend(adapter_collect(source_path, forward))
    if backfill is not None:
        records.extend(adapter_collect(source_path, backfill))

    status = overall_source_status(records)

    inserted = 0
    if not dry_run:
        inserted = repository.insert_records(records)
        if forward is not None:
            repository.set_checkpoint(agent, forward.end_utc)

    return AgentCollectionResult(
        agent=agent, status=status, records_observed=len(records), records_inserted=inserted
    )
```

Update `collect_all` to accept and thread through `configured_start`:

```python
def collect_all(
    *,
    ledger_path: Path,
    hermes_db: Path,
    claude_projects_dir: Path,
    codex_sessions_dir: Path,
    now: datetime,
    configured_start: datetime = DEFAULT_INITIAL_START,
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
                agent,
                adapter_collect,
                source_paths[agent],
                repository,
                now=now,
                dry_run=dry_run,
                configured_start=configured_start,
            )
            for agent, adapter_collect in ADAPTER_COLLECTORS
        ]
    finally:
        repository.close()
```

Also update the module docstring at the top of the file (lines 1-11) to describe the new backfill behavior instead of the old fixed-window one:

```python
"""Pull local agent usage into the private ledger.

Each agent's collection window runs from its last checkpoint up to
``now``, or — on an agent's first-ever collection — from the configured
initial start (``config.initial_collection_start``, default 2026-07-04,
resolved via ``resolve_initial_collection_start``) up to ``now``.

If the configured start predates an agent's earliest already-collected
record, an additional backfill window covers that gap on every run until
it closes — appending older history without moving the forward
checkpoint. ``now`` must always be supplied by the caller rather than
computed here, the same explicit-time convention used throughout this
project (see e.g. ``render_dashboard``'s ``today``/``generated_at``), so
collection stays deterministic and testable.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/commands/test_collect.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tomax/commands/collect.py tests/commands/test_collect.py
git commit -m "feat(collect): add configurable start date and backfill gap window"
```

---

### Task 5: `cli.py` — `config start-date` command + wire into `collect`

**Files:**
- Modify: `src/tomax/cli.py`
- Test: `tests/test_cli.py` (create if it doesn't already cover CLI commands — check first with `ls tests/test_cli.py` or `grep -rl "from typer.testing" tests/`)

**Interfaces:**
- Consumes: `resolve_initial_collection_start` (Task 3), `collect_command.collect_all(..., configured_start=...)` (Task 4).
- Produces: `tomax config start-date --date/--all` command.

- [ ] **Step 1: Check for an existing CLI test harness**

Run: `grep -rl "CliRunner" tests/ 2>/dev/null`

If a file is found (e.g. `tests/test_cli.py`), read it to match its existing style (fixtures for `config_path`/`ledger_path` via `monkeypatch`, etc.) before writing new tests. If none is found, use the pattern in Step 1a below with `typer.testing.CliRunner` and `monkeypatch.setattr` on `tomax.cli.config_file_path`/`ledger_file_path` (mirroring how `config_file_path()`/`ledger_file_path()` are called directly, no dependency injection exists today) — patch them to return `tmp_path` locations.

- [ ] **Step 1a: Write the failing tests**

Create or append to `tests/test_cli.py`:

```python
"""Tests for the tomax CLI."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from tomax import cli

runner = CliRunner()


def test_config_start_date_requires_exactly_one_of_date_or_all(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "config_file_path", lambda: tmp_path / "config.json")

    result = runner.invoke(cli.app, ["config", "start-date"])

    assert result.exit_code != 0


def test_config_start_date_rejects_both_date_and_all(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "config_file_path", lambda: tmp_path / "config.json")

    result = runner.invoke(cli.app, ["config", "start-date", "--date", "2026-01-01", "--all"])

    assert result.exit_code != 0


def test_config_start_date_persists_a_custom_date(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(cli, "config_file_path", lambda: config_path)

    result = runner.invoke(cli.app, ["config", "start-date", "--date", "2026-01-01"])

    assert result.exit_code == 0
    assert json.loads(config_path.read_text())["initial_collection_start"] == "2026-01-01"


def test_config_start_date_persists_all(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(cli, "config_file_path", lambda: config_path)

    result = runner.invoke(cli.app, ["config", "start-date", "--all"])

    assert result.exit_code == 0
    assert json.loads(config_path.read_text())["initial_collection_start"] == "ALL"


def test_config_start_date_rejects_a_malformed_date(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(cli, "config_file_path", lambda: config_path)

    result = runner.invoke(cli.app, ["config", "start-date", "--date", "not-a-date"])

    assert result.exit_code != 0
    assert not config_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `assert 2 == 0` / no such command 'config' (typer reports usage error / missing command).

- [ ] **Step 3: Implement in `cli.py`**

Add imports at the top (alongside existing ones):

```python
from dataclasses import replace
```

```python
from tomax.config import (
    config_file_path,
    data_dir,
    ledger_file_path,
    load_config,
    resolve_initial_collection_start,
    save_config,
)
```

(This replaces the current `from tomax.config import config_file_path, data_dir, ledger_file_path, load_config` line — add `resolve_initial_collection_start` and `save_config`.)

Add the sub-app near the existing `schedule_app` declaration:

```python
config_app = typer.Typer(help="Manage local tomax configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")
```

Add the command (anywhere after `app`/`config_app` are defined, e.g. right after the `doctor` command):

```python
@config_app.command("start-date")
def config_start_date(
    date: str | None = typer.Option(
        None, "--date", help="Custom initial collection start date, in YYYY-MM-DD form."
    ),
    all_history: bool = typer.Option(
        False, "--all", help="Collect all available local history (unbounded start)."
    ),
) -> None:
    """Set how far back the first-ever collection for each agent should reach."""
    if date is not None and all_history:
        raise typer.BadParameter("pass either --date or --all, not both")
    if date is None and not all_history:
        raise typer.BadParameter("pass either --date or --all")

    value = "ALL" if all_history else date
    try:
        config = replace(load_config(config_file_path()), initial_collection_start=value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    save_config(config_file_path(), config)
    typer.echo(f"tomax: initial collection start set to {value}")
```

Update the `collect` command to resolve and pass `configured_start`:

```python
@app.command()
def collect(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview what would be collected without writing to the ledger."
    ),
) -> None:
    """Pull new local agent usage into the private ledger."""
    now = datetime.now(timezone.utc)
    config = load_config(config_file_path())
    configured_start = resolve_initial_collection_start(config.initial_collection_start)
    results = collect_command.collect_all(
        ledger_path=ledger_file_path(),
        hermes_db=DEFAULT_HERMES_STATE_DB,
        claude_projects_dir=DEFAULT_CLAUDE_CODE_PROJECTS_DIR,
        codex_sessions_dir=DEFAULT_CODEX_SESSIONS_DIR,
        now=now,
        configured_start=configured_start,
        dry_run=dry_run,
    )
    for result in results:
        status = result.status.value if result.status is not None else "up to date"
        typer.echo(
            f"  {result.agent.value}: {status} "
            f"(observed {result.records_observed}, inserted {result.records_inserted})"
        )
    if dry_run:
        typer.echo("tomax: dry run, nothing written")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tomax/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'tomax config start-date' and wire it into collect"
```

---

### Task 6: `doctor.py` — surface the configured start date

**Files:**
- Modify: `src/tomax/commands/doctor.py`
- Modify: `src/tomax/cli.py:52-69` (the `doctor` command)
- Test: `tests/commands/test_doctor.py` (check `find tests -iname "*doctor*"` first; if none exists, create it following the style of `tests/commands/test_collect.py`)

**Interfaces:**
- Consumes: `resolve_initial_collection_start` (Task 3), `collection_window(..., configured_start=...)` (Task 4).
- Produces: `DoctorReport.initial_collection_start: str | None` (raw config value, not the resolved datetime).

- [ ] **Step 1: Check for an existing doctor test file**

Run: `find tests -iname "*doctor*" -not -path "*.venv*"`

Read whatever is found to match its fixture style before adding tests. If nothing exists, use the pattern below directly.

- [ ] **Step 2: Write the failing test**

Add to `tests/commands/test_doctor.py` (create the file with this content if it doesn't exist, following the `_source_paths`/`NOW` conventions from `tests/commands/test_collect.py` — import `run_doctor` from `tomax.commands.doctor`):

```python
"""Tests for local configuration and per-agent source diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone

from tomax.commands.doctor import run_doctor
from tomax.config import AppConfig, config_file_path, save_config

UTC = timezone.utc
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_doctor_report_surfaces_the_configured_initial_collection_start(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    save_config(config_path, AppConfig(initial_collection_start="2026-01-01"))

    report = run_doctor(
        config_path=config_path,
        ledger_path=tmp_path / "ledger.sqlite3",
        hermes_db=tmp_path / "missing-hermes.db",
        claude_projects_dir=tmp_path / "missing-claude",
        codex_sessions_dir=tmp_path / "missing-codex",
        now=NOW,
    )

    assert report.initial_collection_start == "2026-01-01"


def test_doctor_report_defaults_initial_collection_start_to_none(tmp_path) -> None:
    report = run_doctor(
        config_path=tmp_path / "missing-config.json",
        ledger_path=tmp_path / "ledger.sqlite3",
        hermes_db=tmp_path / "missing-hermes.db",
        claude_projects_dir=tmp_path / "missing-claude",
        codex_sessions_dir=tmp_path / "missing-codex",
        now=NOW,
    )

    assert report.initial_collection_start is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/commands/test_doctor.py -v`
Expected: FAIL — `TypeError: DoctorReport.__init__() got an unexpected keyword argument` (or `AttributeError` on the assertion).

- [ ] **Step 4: Implement in `doctor.py`**

Update imports:

```python
from tomax.config import load_config, resolve_initial_collection_start
```

Add the field to `DoctorReport`:

```python
@dataclass(frozen=True, slots=True)
class DoctorReport:
    device_id: str
    repo_target: str | None
    display_timezone: str
    initial_collection_start: str | None
    sources: tuple[SourceDiagnostic, ...]
```

Update `run_doctor` to resolve the configured start and pass it into `collection_window`, and populate the new field:

```python
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
        sources=tuple(sources),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/commands/test_doctor.py -v`
Expected: PASS

- [ ] **Step 6: Update the `doctor` CLI command to display the setting**

In `src/tomax/cli.py`, update the `doctor` command body:

```python
@app.command()
def doctor() -> None:
    """Show local configuration and per-agent source health."""
    now = datetime.now(timezone.utc)
    report = doctor_command.run_doctor(
        config_path=config_file_path(),
        ledger_path=ledger_file_path(),
        hermes_db=DEFAULT_HERMES_STATE_DB,
        claude_projects_dir=DEFAULT_CLAUDE_CODE_PROJECTS_DIR,
        codex_sessions_dir=DEFAULT_CODEX_SESSIONS_DIR,
        now=now,
    )
    typer.echo(f"device id: {report.device_id}")
    typer.echo(f"repo target: {report.repo_target or '(not set)'}")
    typer.echo(f"display timezone: {report.display_timezone}")
    typer.echo(f"initial collection start: {report.initial_collection_start or 'default (2026-07-04)'}")
    for source in report.sources:
        status = source.status.value if source.status is not None else "up to date"
        typer.echo(f"  {source.agent.value}: {status}")
```

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests, including Tasks 1-5's)

- [ ] **Step 8: Commit**

```bash
git add src/tomax/commands/doctor.py src/tomax/cli.py tests/commands/test_doctor.py
git commit -m "feat(doctor): surface configured initial collection start"
```

---

## Post-plan verification

- [ ] Run `pytest -v` from the repo root — full suite passes.
- [ ] Run `tomax config start-date --date 2026-01-01` then `tomax doctor` locally — confirm the new line shows `2026-01-01`.
- [ ] Run `tomax config start-date --all` then `tomax doctor` — confirm it shows `ALL`.
- [ ] Run `tomax config start-date --date 2026-01-01 --all` — confirm it's rejected with a clear error and nothing is written.
