"""Shared helpers for local agent-source adapters."""

from __future__ import annotations

import hashlib

_FINGERPRINT_SEPARATOR = "\x1f"

MCP_TOOL_NAME_PREFIX = "mcp__"
_MCP_NAME_DELIM = "__"


def make_fingerprint(*parts: str) -> str:
    """Derive a stable, opaque fingerprint from local source identifiers.

    Adapters must never store a source's raw session/event IDs in normalized
    records. Hashing them here keeps the fingerprint unique and stable for
    deduplication while never exposing the identifier it was built from.
    """
    joined = _FINGERPRINT_SEPARATOR.join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def split_mcp_tool_name(tool_name: str) -> tuple[str, str] | None:
    """Split a ``mcp__<server>__<tool>`` name into (server, tool).

    This convention is shared by Hermes, Claude Code, Codex, and OpenCode
    (confirmed in Hermes's own source, ``tools/mcp_tool.py``). Returns None
    if the name isn't a well-formed MCP tool name.
    """
    if not tool_name.startswith(MCP_TOOL_NAME_PREFIX):
        return None
    remainder = tool_name[len(MCP_TOOL_NAME_PREFIX) :]
    server, delimiter, tool = remainder.partition(_MCP_NAME_DELIM)
    if not delimiter or not server or not tool:
        return None
    return server, tool
