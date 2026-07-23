"""Shared, render-backend-neutral helpers for ranking and bucketing usage counters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

OTHER_LABEL = "Other"


def rank_usage(counters: Mapping[str, int]) -> list[tuple[str, int]]:
    """Return usage counters in the display order used by charts (count desc, then name)."""
    return sorted(counters.items(), key=lambda item: (-item[1], item[0]))


def bucket_top_n(ranked: Sequence[tuple[str, int]], top_n: int) -> list[tuple[str, int]]:
    """Keep the top ``top_n`` ranked entries, summing the rest into one 'Other' entry."""
    kept = list(ranked[:top_n])
    overflow = ranked[top_n:]
    if overflow:
        kept.append((OTHER_LABEL, sum(count for _, count in overflow)))
    return kept
