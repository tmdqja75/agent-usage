"""Public-name privacy filtering for skill and MCP names.

Default policy: skill and MCP names are shown publicly exactly as
observed. A built-in denylist hides names that look like they carry
credentials, secrets, or a leaked filesystem path; users can override it
in both directions with their own allow/block lists (see
:class:`~tomax.config.AppConfig`). Excluded names are replaced with
a single stable hidden-bucket label rather than dropped, so aggregate
counts stay accurate without revealing which name was hidden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tomax.config import AppConfig

HIDDEN_NAME = "(hidden)"

_MAX_PLAUSIBLE_NAME_LENGTH = 200

# Substring matching is deliberately broad: a false-positive hide (e.g. a
# tool legitimately named "tokenizer") costs nothing but a config tweak via
# privacy_allow, while a missed credential-shaped name would leak publicly.
# When in doubt, this list is written to over-hide rather than under-hide.
_BUILTIN_DENYLIST_TERMS = (
    "password",
    "passwd",
    "secret",
    "credential",
    "token",
    "apikey",
    "privatekey",
    "sshkey",
    "accesskey",
    "clientsecret",
)


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_builtin_denylisted(name: str) -> bool:
    """Whether a name matches the built-in sensitive-name denylist.

    Catches credential/secret-shaped keywords, names that look like a
    leaked filesystem path, and implausibly long strings that suggest
    dumped content rather than a real identifier.
    """
    if "/" in name or "\\" in name:
        return True
    if len(name) > _MAX_PLAUSIBLE_NAME_LENGTH:
        return True
    normalized = _normalize(name)
    return any(term in normalized for term in _BUILTIN_DENYLIST_TERMS)


@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    """Resolves whether a skill/MCP name is safe to publish, and under what label.

    Precedence: an explicit user block always hides a name; otherwise an
    explicit user allow always shows it; otherwise the built-in denylist
    decides.
    """

    allow: frozenset[str] = frozenset()
    block: frozenset[str] = frozenset()

    @classmethod
    def from_config(cls, config: AppConfig) -> PrivacyPolicy:
        return cls(allow=frozenset(config.privacy_allow), block=frozenset(config.privacy_block))

    def is_public(self, name: str) -> bool:
        """Whether ``name`` should be published as-is."""
        if name in self.block:
            return False
        if name in self.allow:
            return True
        return not is_builtin_denylisted(name)

    def sanitize(self, name: str | None) -> str | None:
        """Return ``name`` unchanged if public, else the stable hidden bucket."""
        if name is None:
            return None
        return name if self.is_public(name) else HIDDEN_NAME
