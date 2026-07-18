# Agent Usage Dashboard — Validated Specification

## Goal

Create a dedicated, MIT-licensed, public open-source Python CLI for macOS that collects privacy-safe session-usage analytics from **Hermes Agent**, **Claude Code**, and **Codex**. Each user points the tool at a GitHub profile repository, where it renders a static Markdown/SVG dashboard in `README.md`.

The initial target profile repository is `tmdqja75/tmdqja75`.

## Confirmed product decisions

- **Official first-release platform:** macOS.
- **Required adapters:** Hermes Agent, Claude Code, and Codex.
- **Headline token total:** `input_tokens + output_tokens + reasoning_tokens`.
- Cache read/write tokens may remain in private diagnostics but never inflate the headline total.
- **Initial backfill:** exactly the two-week period beginning **2026-07-04**; no unrequested historic scan.
- **Refresh model:** manual CLI plus opt-in daily local scheduling.
- **Public privacy policy:** exact skill/MCP names by default, subject to built-in denylist plus user allow/block overrides.
- **Dashboard content:** privacy-safe activity dashboard: sessions/active days, 14-day trend, agent comparison, distinct skills/MCPs, top general tools, visualizations, and lifetime metrics since tracking began.
- **Permanent storage:** hybrid. Private normalized records live in local SQLite; public sanitized daily aggregates are versioned in the profile repository.
- **Multi-device:** all devices contribute sanitized per-device aggregates to one profile repository; GitHub Actions produces the final merged README dashboard.
- **Distribution:** dedicated public installable Python CLI, not scripts embedded in the profile repository.

## Source discovery findings

| Agent | Local source | Usable accounting signal | Current status during discovery |
|---|---|---|---|
| Hermes Agent | local state database | session token fields; tool-call records in messages | Available with activity |
| Claude Code | project transcripts | Per-turn usage and native tool records when transcripts exist | Source unavailable on this machine; history alone is insufficient |
| Codex | session rollout JSONL | `token_count` events; native/custom tool records | Available, but no rollout inside the initial 14-day window |

Adapter statuses must always distinguish:

1. `available_with_activity`
2. `available_with_zero_activity`
3. `source_unavailable`

Never show unavailable as zero.

---

## Architecture

### 1. Local collection

Adapters read local state **read-only** and normalize only safe metadata:

- agent name
- UTC occurrence timestamp
- opaque local session/event fingerprint
- input/output/reasoning tokens
- observed skill name
- observed MCP server/tool name
- source status and schema version

They never retain or publish prompts, transcripts, paths, repository names, credentials, raw session IDs, device names, or raw tool arguments.

### 2. Private canonical ledger

Each installation has a local SQLite ledger under a standard macOS Application Support location. It stores normalized records, checkpoints, deduplication data, configuration, and a random opaque device ID.

### 3. Public sanitized daily aggregates

Each device writes only its own records at:

```text
data/v1/devices/<opaque-device-id>/<YYYY-MM-DD>.json
```

A daily record contains schema/version metadata, checksum, safe agent token/session totals, skill/MCP counters, and status—not raw events. Same-day writes are idempotent; later dates are treated as immutable except for controlled late data repair.

### 4. GitHub aggregation

A profile-repository GitHub Action validates all public records, aggregates device partitions, renders README markers and static SVGs, and commits only meaningful changes. It runs with `contents: write` and a concurrency lock.

### 5. README dashboard

Render only static Markdown and relative SVG assets. Include:

- data freshness and adapter health
- rolling 14-day input/output/reasoning totals
- rolling sessions, active days, distinct skills, and distinct MCP servers
- per-agent comparison
- 14-day activity/token trend SVG
- lifetime totals since first collection
- cumulative lifetime and monthly trend SVGs
- safe skill/MCP leaderboards and optional top general tools

Use stable managed markers:

```html
<!-- agent-usage:start -->
<!-- agent-usage:end -->
```

Preserve all README text outside those markers.
