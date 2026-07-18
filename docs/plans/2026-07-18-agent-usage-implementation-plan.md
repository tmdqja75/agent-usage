# Agent Usage Dashboard — Validated Specification & Implementation Plan

> **Implementation note:** Use the `subagent-driven-development` workflow task-by-task once implementation is explicitly authorized.

## Goal

Create a dedicated, MIT-licensed, public open-source Python CLI for macOS that collects privacy-safe session-usage analytics from **Hermes Agent**, **Claude Code**, and **Codex**. Each user points the tool at a GitHub profile repository, where it renders a static Markdown/SVG dashboard in `README.md`.

The initial target profile repository is `tmdqja75/tmdqja75`. The collector repository has not yet been named or created.

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
| Hermes Agent | `~/.hermes/state.db` | `sessions` token fields; tool-call records in `messages` | Available with activity |
| Claude Code | `~/.claude/projects/**` transcripts | Per-turn usage and native tool records when transcripts exist | Source unavailable on this machine; `history.jsonl` alone is insufficient |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | `token_count` events; native/custom tool records | Available, but no rollout inside the initial 14-day window |

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

---

# Implementation Plan

**Proposed repository root:** `<collector-repo>/` (choose the actual name/path before implementation)

**Tech stack:** Python 3.11+, `uv`, `pytest`, `ruff`, `platformdirs`, `typer`, standard-library SQLite/JSON/SVG generation, `git`, `gh`, and macOS `launchd`.

## Phase 0 — Foundation

### Task 1: Package skeleton

**Create**

- `pyproject.toml`
- `src/agent_usage/__init__.py`
- `src/agent_usage/cli.py`
- `tests/test_smoke.py`
- `README.md`, `LICENSE`, `.gitignore`

**Steps**

1. Configure Python `>=3.11`, `src/` layout, and `agent-usage` console entry point.
2. Add `pytest` and `ruff` development tooling.
3. Write a failing `agent-usage --help` smoke test.
4. Implement the minimum Typer command group.
5. Verify with `uv run pytest tests/test_smoke.py -q` and `uv run ruff check .`.
6. Commit `chore: scaffold agent usage cli`.

### Task 2: Shared models and time windows

**Create**

- `src/agent_usage/models.py`
- `src/agent_usage/time_window.py`
- `tests/test_models.py`
- `tests/test_time_window.py`

**Steps**

1. Define normalized agent/status/token models.
2. Test the requested two-week initial collection boundary.
3. Store public day boundaries in UTC while supporting a configurable display timezone.
4. Commit `feat: add normalized usage models`.

## Phase 1 — Private local ledger

### Task 3: SQLite ledger and deduplication

**Create**

- `src/agent_usage/ledger/schema.py`
- `src/agent_usage/ledger/repository.py`
- `tests/ledger/test_repository.py`

**Steps**

1. Write tests for normalized records, source statuses, checkpoints, and duplicate rejection.
2. Create local tables for events/sessions, daily aggregates, device identity, and migrations.
3. Add a unique opaque fingerprint constraint.
4. Verify repeat imports leave totals unchanged.
5. Commit `feat: add private usage ledger`.

### Task 4: Configuration and opaque device identity

**Create**

- `src/agent_usage/config.py`
- `tests/test_config.py`

**Steps**

1. Use `platformdirs` for macOS config/data locations.
2. Generate a random UUID per install.
3. Store repo target, privacy overrides, timezone, and scheduling preferences locally.
4. Assert configuration contains no GitHub token, hostname, or raw agent path.
5. Commit `feat: add private configuration and device identity`.

## Phase 2 — Agent adapters

### Task 5: Hermes adapter

**Create**

- `src/agent_usage/adapters/base.py`
- `src/agent_usage/adapters/hermes.py`
- `tests/adapters/test_hermes.py`
- `tests/fixtures/hermes_state.db`

**Steps**

1. Create anonymized SQLite fixtures for the observed `sessions`, `messages`, and `session_model_usage` data shape.
2. Test input/output/reasoning totals, cutoff filtering, unavailable source, zero activity, `skill_view(name)` counts, and `mcp__server__tool` parsing.
3. Open source databases read-only and parse only required safe call fields.
4. Commit `feat: collect Hermes usage`.

### Task 6: Claude Code adapter

**Create**

- `src/agent_usage/adapters/claude_code.py`
- `tests/adapters/test_claude_code.py`
- `tests/fixtures/claude_projects/`

**Steps**

1. Add sanitized project-transcript fixtures with per-turn usage and native skill/MCP calls.
2. Test that history-only data is unavailable rather than zero.
3. Parse only `~/.claude/projects/` session transcripts; do not estimate absent token data.
4. Add schema-variation diagnostics.
5. Commit `feat: collect Claude Code usage`.

### Task 7: Codex adapter

**Create**

- `src/agent_usage/adapters/codex.py`
- `tests/adapters/test_codex.py`
- `tests/fixtures/codex_sessions/`

**Steps**

1. Add sanitized rollout fixtures with cumulative `token_count` snapshots.
2. Write a regression test ensuring snapshots become monotonic per-session deltas, not summed totals.
3. Test counter resets, malformed lines, and empty window behavior.
4. Count skill/MCP calls only for explicitly confirmed conventions; do not mislabel shell/editor tools as MCP.
5. Commit `feat: collect Codex usage`.

## Phase 3 — Privacy and durable public data

### Task 8: Privacy filtering

**Create**

- `src/agent_usage/privacy.py`
- `tests/test_privacy.py`

**Steps**

1. Implement a built-in sensitive-name denylist.
2. Add user allow/block overrides.
3. Replace excluded names with a stable hidden bucket.
4. Test public output does not contain fixture prompts, paths, repos, IDs, hostnames, or arguments.
5. Commit `feat: add public-name privacy controls`.

### Task 9: Daily public-record export

**Create**

- `src/agent_usage/public_data.py`
- `tests/test_public_data.py`

**Steps**

1. Create the device/day JSON schema.
2. Include schema version, checksum, safe counts, source statuses, skills, and MCPs.
3. Test idempotent same-day rewrites and record-size limits.
4. Test private data cannot cross the export boundary.
5. Commit `feat: export sanitized daily aggregates`.

### Task 10: Multi-device aggregation

**Create**

- `src/agent_usage/aggregate.py`
- `tests/test_aggregate.py`

**Steps**

1. Aggregate multiple device partitions.
2. Validate schema, checksums, dates, record sizes, and non-negative totals.
3. Reject malformed/future-dated records with diagnostics.
4. Produce rolling 14-day and lifetime summaries.
5. Commit `feat: aggregate multi-device usage history`.

## Phase 4 — Dashboard renderer and GitHub workflow

### Task 11: README and SVG renderer

**Create**

- `src/agent_usage/render/markdown.py`
- `src/agent_usage/render/svg.py`
- `templates/profile-readme.md`
- `tests/render/test_markdown.py`
- `tests/render/test_svg.py`

**Steps**

1. Render source health, rolling/lifetime metrics, agent table, and skill/MCP leaderboards.
2. Generate `assets/agent-usage/rolling-14d.svg` and `assets/agent-usage/lifetime.svg`.
3. Test valid Markdown, idempotent markers, deterministic SVG, and activity/zero/unavailable states.
4. Commit `feat: render README dashboard and charts`.

### Task 12: GitHub Action template

**Create**

- `templates/github-workflow.yml`
- `scripts/build_profile_dashboard.py`
- `tests/test_workflow_template.py`

**Steps**

1. Trigger only on direct default-branch changes to `data/v1/**`.
2. Use `contents: write` and serialized action concurrency.
3. Validate public records and regenerate only changed README/assets.
4. Prevent loops by excluding generated README/assets from trigger paths.
5. Commit `feat: add serialized dashboard workflow`.

## Phase 5 — CLI, publishing, scheduler, and documentation

### Task 13: Local CLI commands

**Create**

- `src/agent_usage/commands/init.py`
- `src/agent_usage/commands/collect.py`
- `src/agent_usage/commands/render.py`
- `src/agent_usage/commands/doctor.py`
- `tests/commands/`

**Commands**

```bash
agent-usage init --repo OWNER/PROFILE-REPO
agent-usage doctor
agent-usage collect
agent-usage render
agent-usage collect --dry-run
```

Test that unavailable and zero sources differ and dry-run has no side effects. Commit `feat: add collection and diagnostics commands`.

### Task 14: Safe Git publishing

**Create**

- `src/agent_usage/publish/git.py`
- `src/agent_usage/commands/publish.py`
- `tests/publish/test_git.py`

**Steps**

1. Require `gh auth status` before remote actions.
2. Write only the installation’s own device partition.
3. Implement fetch, commit, pull/rebase, and bounded push retry.
4. Test no-op publish, conflict recovery, and no force-push.
5. Commit `feat: publish device aggregates safely`.

### Task 15: macOS launchd schedule

**Create**

- `src/agent_usage/schedule/launchd.py`
- `src/agent_usage/commands/schedule.py`
- `tests/schedule/test_launchd.py`

**Commands**

```bash
agent-usage schedule install --daily-at 09:00
agent-usage schedule status
agent-usage schedule remove
```

Test generated plist content, local logs, and equivalence to `collect && publish`. Commit `feat: add macOS daily scheduler`.

### Task 16: Documentation and release verification

**Create**

- `docs/privacy.md`
- `docs/multi-device.md`
- `docs/troubleshooting.md`
- `.github/workflows/ci.yml`

**Required checks**

```bash
uv run pytest -q
uv run ruff check .
uv build
agent-usage --help
```

Release acceptance must prove:

- only the requested initial two-week interval is backfilled;
- repeat runs do not double-count;
- a second device aggregates correctly;
- unavailable sources are never rendered as zero;
- generated output has no sensitive fixture values;
- launchd install/removal works; and
- the profile action regenerates the dashboard from public aggregates.

Commit `docs: add setup privacy and multi-device guidance`.

---

## Approval boundary

Do not create the public collector repository, modify `tmdqja75/tmdqja75`, install the package, configure launchd, or publish any data until the user explicitly authorizes implementation in a new session.
