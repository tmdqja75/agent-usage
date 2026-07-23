# AGENTS.md

Guidance for AI agents and contributors working in this repository.

## What this project is

`agent-usage` is a macOS-first Python CLI that builds privacy-conscious, local
usage summaries for **Hermes Agent**, **Claude Code**, and **Codex**. It reads
each supported local source read-only, normalizes only aggregation metadata, and
keeps a private SQLite ledger. Optional publishing writes sanitized per-device,
per-UTC-day aggregates to a GitHub profile repository.

See [README.md](README.md) for the user-facing guide.

## Environment and commands

- Python `>=3.11`. Dependency and task runner: [uv](https://docs.astral.sh/uv/).
- Run tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Build: `uv build`
- CLI help: `uv run agent-usage --help`

### CLI commands

| Command | Purpose |
| --- | --- |
| `doctor` | Read-only diagnostics; no ledger writes, no checkpoint advance. |
| `collect` | Read sources and persist normalized records (`--dry-run` to preview). |
| `render` | Write a fully local Plotly PNG dashboard preview (no network). |
| `dashboard` | Serve an interactive localhost chart dashboard (see below). |
| `publish` | Stage and push this device's sanitized aggregates (opt-in, `gh` auth). |
| `init` | Local-only: record `OWNER/REPO` target, ensure device ID. |
| `schedule` | Install/remove a `launchd` daily collect+publish job. |

## Repository layout

- `src/agent_usage/` — package source.
  - `aggregate.py` — validation, rolling windows, daily/token totals, record aggregation.
  - `render/` — chart backends. `plotly.py` (PNG), `dashboard_data.py` (interactive
    `data.json` builder), `_counters.py` (shared rank/bucket helpers, backend-neutral).
  - `dashboard/` — interactive dashboard: `payload.py` (assemble data.json from local
    or multi-device), `remote.py` (shallow-clone multi-device fetch), `server.py`
    (stdlib loopback HTTP server), `ui_build.py` (on-demand UI build with caching).
  - `commands/` — one module per CLI command; `cli.py` wires them with Typer.
  - `ledger/`, `publish/`, `privacy.py`, `public_data.py`, `config.py`, `models.py`.
- `dashboard-ui/` — React + Vite + visx source for the interactive dashboard. Built
  on demand by `dashboard/ui_build.py`; `node_modules/` and `dist/` are gitignored.
- `tests/` — mirrors the package (`tests/render/`, `tests/dashboard/`, `tests/commands/`).
  Test dirs use no `__init__.py`.
- `docs/` — privacy boundary, multi-device rules, troubleshooting, plans/specs.

## Conventions

- Every new Python module starts with `from __future__ import annotations`.
- Match the surrounding code's style, naming, and comment density.
- TDD: write a failing test first, then implement. Commit per logical unit.
- The interactive dashboard server binds `127.0.0.1` only — never `0.0.0.0`.
- Multi-device data is fetched only by shallow `git clone` of the profile repo —
  never the GitHub API.
- `source_unavailable` is never treated as zero activity.

## Dashboard UI constraints (hard)

- Page background is exactly `#090A0B`; each chart block background is exactly
  `#0E0F13`.
- **No colored or gradient backgrounds / gradient blocks anywhere.** The only
  permitted gradients are those internal to a chart component's own default
  rendering — keep those intact.
- `data.json` contract keys: `window {start,end}`, `tokens [{date,input,output,
  reasoning}]`, `agents [{agent,tokens}]`, `skills [{name,count}]`,
  `mcp [{name,count}]`, `heatmap [{date,tokens}]`.
- Skills/MCP donuts bucket beyond `--pie-top-n` (default 6) into one `Other` entry.
