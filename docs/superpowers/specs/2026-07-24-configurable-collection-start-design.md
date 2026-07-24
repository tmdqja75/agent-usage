# Configurable collection start date

## Problem

First-run collection window is hardcoded (`INITIAL_COLLECTION_WINDOW`,
2026-07-04 through 2026-07-18) in `time_window.py`. Users cannot choose
how far back their initial backfill goes, nor collect their full local
history. Applies to both manual `agent-usage collect` and the launchd
daily schedule (same code path, same config).

## Config

`AppConfig` gains one field:

```python
initial_collection_start: str | None = None
```

- `None` — default, current hardcoded start date (2026-07-04).
- `"ALL"` — literal sentinel, unbounded backfill (see `EPOCH_START` below).
- `"YYYY-MM-DD"` — custom start date.

Validated in `AppConfig.__post_init__`: must be `None`, `"ALL"`, or a
parseable ISO date. Invalid values raise `ValueError`, same pattern as
existing `display_timezone`/`schedule_time` validation.

## CLI

New `agent-usage config` typer sub-app, alongside existing `schedule`
sub-app:

```
agent-usage config start-date --date 2026-01-01
agent-usage config start-date --all
```

Mutually exclusive; exactly one required (`typer.BadParameter` otherwise).
Persists via existing `save_config`.

`doctor` command gains a line showing the current setting.

## time_window.py

- Drop the fixed end (2026-07-18) from `INITIAL_COLLECTION_WINDOW`. A
  first-ever run for an agent now always windows `configured_start → now`
  — no artificial cap, since the cap existed only to bound the *old*
  fixed default.
- Add `EPOCH_START = datetime(1970, 1, 1, tzinfo=UTC)`, used when config
  is `"ALL"`.
- `cli.py` resolves the config value (`None`/`"ALL"`/date string) to a
  concrete `datetime` before calling `collect_all`.

## collect.py — gap-fill

Checkpoint (`repository.get_checkpoint` / `set_checkpoint`) keeps its
current meaning: a forward-only "last collected up to here" pointer per
agent. It is never reset when the start-date config changes.

Per-agent, per-run, `collect_agent` builds up to two windows:

1. **Forward** — `[checkpoint, now]` if a checkpoint exists, else
   `[configured_start, now]` on an agent's first-ever collection.
2. **Backfill gap** — if the agent already has records and its earliest
   existing record's timestamp is later than `configured_start`, an
   additional window `[configured_start, earliest_existing)` is
   collected and inserted. This has no checkpoint of its own: once the
   gap closes (earliest existing record reaches `configured_start`),
   the comparison naturally stops producing a window on later runs —
   idempotent, no new state needed.

Both windows call the same `adapter_collect`, insert into the ledger,
and their `records_observed`/`records_inserted` are summed into one
`AgentCollectionResult` per agent (existing shape unchanged). Only the
forward window's end advances the checkpoint.

## Repository

New method on `LedgerRepository`:

```python
def get_earliest_record_at(self, agent: SupportedAgent) -> datetime | None:
    """MIN(occurred_at) across this agent's records, or None if it has none."""
```

## Out of scope

- No UI/dashboard changes.
- No migration of existing config files (new field defaults to `None`,
  old behavior preserved until user opts in).
- No change to `publish`/`dashboard` commands.
