# Privacy model

`tomax` is designed to produce usage summaries without collecting or publishing session content. The first release is macOS-only and reads supported local agent sources **read-only**.

## What stays local

The private SQLite ledger and local configuration retain only the normalized data needed to deduplicate and aggregate usage:

- supported agent name;
- UTC occurrence time;
- opaque event and session fingerprints;
- input, output, and reasoning token counters;
- observed skill and MCP names; and
- source status and schema version.

The collector does not retain or publish prompts, transcripts, repository names, source paths, raw session IDs, machine names, credentials, or raw tool arguments. The local configuration stores a profile-repository target, display timezone, privacy overrides, and scheduling preference; it does not store a GitHub token, hostname, or agent-source path.

## What can be public

Publishing writes only a device's sanitized daily aggregates at:

```text
data/v1/devices/<opaque-device-id>/<YYYY-MM-DD>.json
```

A public record has a schema version, checksum, per-agent token and session totals, source statuses, and privacy-filtered skill/MCP counters. It never contains raw events, fingerprints, transcript content, prompts, or source paths.

The headline total is exactly `input_tokens + output_tokens + reasoning_tokens`. Cache read/write counters never inflate it.

## Source health is not a token estimate

Each agent/day is explicitly one of:

- `available_with_activity`
- `available_with_zero_activity`
- `source_unavailable`

`source_unavailable` is not displayed or aggregated as zero. In particular, absent Claude Code project transcripts do not justify a token estimate.

## Names and overrides

Skill and MCP names are shown by default only after the built-in sensitive-name denylist and local overrides are applied. Blocked names become a stable hidden bucket. An explicit block wins over an explicit allow; an allow can otherwise override the built-in denylist. Keep overrides local and review them before publishing if a name could identify a person, customer, repository, or secret-bearing integration.

## Before publishing

Use `tomax collect --dry-run` to inspect collection status without changing the ledger. Use `tomax render` for a local preview. Do not put real session fixtures, transcripts, credentials, raw identifiers, or local paths in the collector repository or the profile repository.
