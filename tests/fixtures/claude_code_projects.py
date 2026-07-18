"""Builds synthetic, anonymized Claude Code project-transcript fixtures.

Mirrors the subset of the real ``~/.claude/projects/<project>/<session>.jsonl``
line schema that the Claude Code adapter reads. All values passed in by
tests are synthetic; nothing here originates from real transcript data.
"""

from __future__ import annotations

import json
from pathlib import Path


def write_transcript(path: Path, events: list[dict]) -> None:
    """Write a synthetic Claude Code transcript JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def assistant_event(
    *,
    uuid: str,
    session_id: str,
    timestamp: str,
    model: str = "synthetic-model",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    tool_use: list[dict] | None = None,
    is_sidechain: bool = False,
    usage: dict | None = "__default__",
) -> dict:
    content = list(tool_use or [])
    if not content:
        content = [{"type": "text", "text": "[synthetic assistant response]"}]

    if usage == "__default__":
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
        }

    message = {
        "model": model,
        "role": "assistant",
        "content": content,
    }
    if usage is not None:
        message["usage"] = usage

    return {
        "type": "assistant",
        "uuid": uuid,
        "sessionId": session_id,
        "session_id": session_id,
        "timestamp": timestamp,
        "isSidechain": is_sidechain,
        "message": message,
    }


def user_event(*, uuid: str, session_id: str, timestamp: str, content: str = "[synthetic user message]") -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "sessionId": session_id,
        "timestamp": timestamp,
        "isSidechain": False,
        "message": {"role": "user", "content": content},
    }


def skill_tool_use(tool_use_id: str, skill_name: str) -> dict:
    return {
        "type": "tool_use",
        "id": tool_use_id,
        "name": "Skill",
        "input": {"skill": skill_name},
    }


def mcp_tool_use(tool_use_id: str, tool_name: str) -> dict:
    return {
        "type": "tool_use",
        "id": tool_use_id,
        "name": tool_name,
        "input": {},
    }


def native_tool_use(tool_use_id: str, tool_name: str = "Bash") -> dict:
    return {
        "type": "tool_use",
        "id": tool_use_id,
        "name": tool_name,
        "input": {"command": "echo synthetic"},
    }
