"""Read/write access to the private local usage ledger."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from agent_usage.ledger.schema import apply_schema
from agent_usage.models import NormalizedUsageRecord, SourceStatus, SupportedAgent, TokenUsage
from agent_usage.time_window import normalize_utc

_INSERT_EVENT_SQL = """
INSERT OR IGNORE INTO events (
    fingerprint, agent, occurred_at,
    input_tokens, output_tokens, reasoning_tokens,
    observed_skill_name, observed_mcp_server_name, observed_mcp_tool_name,
    source_status, schema_version
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_UPSERT_CHECKPOINT_SQL = """
INSERT INTO checkpoints (agent, last_collected_at) VALUES (?, ?)
ON CONFLICT(agent) DO UPDATE SET last_collected_at = excluded.last_collected_at
"""


def _record_to_row(record: NormalizedUsageRecord) -> tuple:
    tokens = record.tokens
    return (
        record.fingerprint,
        record.agent.value,
        record.occurred_at.isoformat(),
        tokens.input_tokens if tokens is not None else None,
        tokens.output_tokens if tokens is not None else None,
        tokens.reasoning_tokens if tokens is not None else None,
        record.observed_skill_name,
        record.observed_mcp_server_name,
        record.observed_mcp_tool_name,
        record.source_status.value,
        record.schema_version,
    )


def _row_to_record(row: sqlite3.Row) -> NormalizedUsageRecord:
    source_status = SourceStatus(row["source_status"])
    if source_status is SourceStatus.SOURCE_UNAVAILABLE:
        tokens = None
    else:
        tokens = TokenUsage(
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reasoning_tokens=row["reasoning_tokens"],
        )
    return NormalizedUsageRecord(
        agent=SupportedAgent(row["agent"]),
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        fingerprint=row["fingerprint"],
        tokens=tokens,
        observed_skill_name=row["observed_skill_name"],
        observed_mcp_server_name=row["observed_mcp_server_name"],
        observed_mcp_tool_name=row["observed_mcp_tool_name"],
        source_status=source_status,
        schema_version=row["schema_version"],
    )


class LedgerRepository:
    """Local SQLite-backed store for normalized usage records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        connection.row_factory = sqlite3.Row
        self._connection = connection
        apply_schema(self._connection)

    @classmethod
    def open(cls, path: Path) -> "LedgerRepository":
        """Open (or create) the ledger database at the given path, read-write."""
        return cls(sqlite3.connect(path))

    def close(self) -> None:
        self._connection.close()

    def insert_records(self, records: Iterable[NormalizedUsageRecord]) -> int:
        """Insert records, skipping ones whose fingerprint is already stored.

        Returns the number of newly inserted records, so repeat imports of the
        same records are observably idempotent.
        """
        inserted = 0
        with self._connection:
            for record in records:
                cursor = self._connection.execute(_INSERT_EVENT_SQL, _record_to_row(record))
                inserted += cursor.rowcount
        return inserted

    def list_records(
        self, agent: SupportedAgent | None = None
    ) -> list[NormalizedUsageRecord]:
        """Return stored records, optionally filtered to a single agent."""
        if agent is None:
            rows = self._connection.execute(
                "SELECT * FROM events ORDER BY occurred_at"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM events WHERE agent = ? ORDER BY occurred_at",
                (agent.value,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_checkpoint(self, agent: SupportedAgent) -> datetime | None:
        """Return the last collected instant for an agent, or None if unset."""
        row = self._connection.execute(
            "SELECT last_collected_at FROM checkpoints WHERE agent = ?",
            (agent.value,),
        ).fetchone()
        if row is None:
            return None
        return normalize_utc(datetime.fromisoformat(row["last_collected_at"]))

    def set_checkpoint(self, agent: SupportedAgent, occurred_at: datetime) -> None:
        """Record the latest collected instant for an agent."""
        occurred_at_utc = normalize_utc(occurred_at)
        with self._connection:
            self._connection.execute(
                _UPSERT_CHECKPOINT_SQL, (agent.value, occurred_at_utc.isoformat())
            )
