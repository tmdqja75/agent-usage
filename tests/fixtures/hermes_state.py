"""Builds synthetic, anonymized Hermes ``state.db`` fixtures for adapter tests.

Mirrors the subset of the real ``sessions``, ``messages``, and
``session_model_usage`` schema that the Hermes adapter reads. All values
passed in by tests are synthetic; nothing here originates from real session
data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_CREATE_SESSIONS = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0
)
"""

_CREATE_MESSAGES = """
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER
)
"""

_CREATE_SESSION_MODEL_USAGE = """
CREATE TABLE session_model_usage (
    session_id TEXT NOT NULL,
    model TEXT NOT NULL,
    billing_provider TEXT NOT NULL DEFAULT '',
    billing_base_url TEXT NOT NULL DEFAULT '',
    billing_mode TEXT NOT NULL DEFAULT '',
    task TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    first_seen REAL,
    last_seen REAL,
    PRIMARY KEY (session_id, model, billing_provider, billing_base_url, billing_mode, task)
)
"""


def build_hermes_state_db(
    path: Path,
    *,
    sessions: list[dict] = (),
    messages: list[dict] = (),
    session_model_usage: list[dict] = (),
) -> None:
    """Write a synthetic Hermes-shaped SQLite database to ``path``."""
    connection = sqlite3.connect(path)
    try:
        connection.execute(_CREATE_SESSIONS)
        connection.execute(_CREATE_MESSAGES)
        connection.execute(_CREATE_SESSION_MODEL_USAGE)

        for session in sessions:
            connection.execute(
                """
                INSERT INTO sessions (
                    id, source, started_at, ended_at,
                    input_tokens, output_tokens, reasoning_tokens,
                    cache_read_tokens, cache_write_tokens
                ) VALUES (
                    :id, :source, :started_at, :ended_at,
                    :input_tokens, :output_tokens, :reasoning_tokens,
                    :cache_read_tokens, :cache_write_tokens
                )
                """,
                {
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "ended_at": None,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    **session,
                },
            )

        for message in messages:
            connection.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, tool_call_id, tool_calls,
                    tool_name, timestamp, token_count
                ) VALUES (
                    :id, :session_id, :role, :content, :tool_call_id, :tool_calls,
                    :tool_name, :timestamp, :token_count
                )
                """,
                {
                    "content": None,
                    "tool_call_id": None,
                    "tool_calls": None,
                    "tool_name": None,
                    "token_count": None,
                    **message,
                },
            )

        for usage in session_model_usage:
            connection.execute(
                """
                INSERT INTO session_model_usage (
                    session_id, model, billing_provider, billing_base_url,
                    billing_mode, task, input_tokens, output_tokens,
                    reasoning_tokens, cache_read_tokens, cache_write_tokens,
                    first_seen, last_seen
                ) VALUES (
                    :session_id, :model, :billing_provider, :billing_base_url,
                    :billing_mode, :task, :input_tokens, :output_tokens,
                    :reasoning_tokens, :cache_read_tokens, :cache_write_tokens,
                    :first_seen, :last_seen
                )
                """,
                {
                    "billing_provider": "",
                    "billing_base_url": "",
                    "billing_mode": "",
                    "task": "",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "first_seen": usage.get("last_seen"),
                    **usage,
                },
            )

        connection.commit()
    finally:
        connection.close()
