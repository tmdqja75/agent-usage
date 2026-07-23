# Interactive Localhost Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `agent-usage dashboard` command that serves an interactive localhost chart dashboard (bklit React charts) from local session data by default, or from multi-device data cloned from the GitHub profile repo with `--all-devices`.

**Architecture:** A pure Python data builder turns validated daily payloads (the same ones the Plotly path uses) into one `data.json`. Two source paths feed it: the local ledger, or a shallow `git clone` of the profile repo. Each time the `dashboard` command runs it builds the React UI on demand (cached; rebuilt only when the UI source changed), then a stdlib `http.server` serves that fresh build plus the in-memory `data.json`; the browser fetches `/data.json` when the page opens. The existing Plotly PNG dashboard is untouched.

**Tech Stack:** Python 3.11, Typer, stdlib `http.server`/`webbrowser`; React + Vite + bklit (visx) for the UI, built to a committed `dist/`.

## Global Constraints

- Python floor: `>=3.11`. No new Python runtime dependency (server uses only stdlib).
- The UI is **built on demand** when `dashboard` runs — never a hand-built, committed bundle. Node.js + pnpm (or npm) must be installed to run the command; the build output (`dashboard-ui/dist/`) is a cached, gitignored artifact, rebuilt only when the UI source is newer.
- `from __future__ import annotations` at the top of every new Python module (matches repo style).
- Multi-device data is fetched **only** by shallow `git clone` of `config.repo_target`; never GitHub API.
- Server binds `127.0.0.1` only (never `0.0.0.0`).
- Dashboard page background is exactly `#090A0B`; each chart block background is exactly `#0E0F13`.
- **No colored or gradient backgrounds / gradient blocks anywhere.** The only permitted gradients are those internal to a bklit chart's own default design (e.g. area fill) — keep those intact.
- Skills/MCP donuts bucket beyond `--pie-top-n` (default 6) into a single `"Other"` entry, reusing existing helpers.
- `data.json` contract (exact keys): `window {start,end}`, `tokens [{date,input,output,reasoning}]`, `agents [{agent,tokens}]`, `skills [{name,count}]`, `mcp [{name,count}]`, `heatmap [{date,tokens}]`.

---

### Task 1: Extract shared counter helpers

Move `rank_usage`, `bucket_top_n`, and `_OTHER_LABEL` out of `render/plotly.py` into a neutral module so the interactive path does not import the Plotly/Kaleido module. Re-export from `plotly.py` so its existing behavior and tests are unchanged.

**Files:**
- Create: `src/agent_usage/render/_counters.py`
- Modify: `src/agent_usage/render/plotly.py` (remove the three definitions, import them instead)
- Test: `tests/render/test_counters.py`

**Interfaces:**
- Produces: `rank_usage(counters: Mapping[str, int]) -> list[tuple[str, int]]`; `bucket_top_n(ranked: Sequence[tuple[str, int]], top_n: int) -> list[tuple[str, int]]`; `OTHER_LABEL: str` (renamed public constant, `= "Other"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/render/test_counters.py
from agent_usage.render._counters import OTHER_LABEL, bucket_top_n, rank_usage


def test_rank_usage_orders_by_count_then_name():
    ranked = rank_usage({"b": 1, "a": 3, "c": 3})
    assert ranked == [("a", 3), ("c", 3), ("b", 1)]


def test_bucket_top_n_folds_overflow_into_other():
    ranked = [("a", 5), ("b", 4), ("c", 3), ("d", 2)]
    assert bucket_top_n(ranked, 2) == [("a", 5), ("b", 4), (OTHER_LABEL, 5)]


def test_bucket_top_n_no_overflow_keeps_all():
    ranked = [("a", 5), ("b", 4)]
    assert bucket_top_n(ranked, 2) == [("a", 5), ("b", 4)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/render/test_counters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_usage.render._counters'`

- [ ] **Step 3: Create the shared module**

```python
# src/agent_usage/render/_counters.py
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
```

- [ ] **Step 4: Point `plotly.py` at the shared module**

In `src/agent_usage/render/plotly.py`, delete the local `rank_usage`, `bucket_top_n`, `_OTHER_LABEL` definitions. Add near the other imports:

```python
from agent_usage.render._counters import OTHER_LABEL as _OTHER_LABEL
from agent_usage.render._counters import bucket_top_n, rank_usage
```

Keep the `_OTHER_LABEL` alias so any existing internal references in `plotly.py` still resolve.

- [ ] **Step 5: Run the full render test suite to verify no regression**

Run: `uv run pytest tests/render/ -v`
Expected: PASS (both the new counter tests and the existing plotly tests)

- [ ] **Step 6: Commit**

```bash
git add src/agent_usage/render/_counters.py src/agent_usage/render/plotly.py tests/render/test_counters.py
git commit -m "refactor: extract shared usage-counter helpers from plotly"
```

---

### Task 2: Dashboard data builder

A pure function that turns validated daily payloads into the `data.json` dict. Reuses existing aggregate helpers (`rolling_window`, `daily_token_totals`, `daily_totals`, `aggregate_records`) and the Task 1 counter helpers.

**Files:**
- Create: `src/agent_usage/render/dashboard_data.py`
- Test: `tests/render/test_dashboard_data.py`

**Interfaces:**
- Consumes: `agent_usage.aggregate.{rolling_window, daily_token_totals, daily_totals, aggregate_records}`; `agent_usage.render._counters.{rank_usage, bucket_top_n}`; `agent_usage.models.SupportedAgent`.
- Produces: `build_dashboard_data(valid_payloads: list[dict], *, today: datetime.date, window_days: int = 14, pie_top_n: int = 6) -> dict`.

Semantics:
- `tokens` (Area): the rolling `window_days`-day window ending `today`, via `daily_token_totals`; emit one sorted entry per date whose value is not `None` (a `None` day means no available source and is skipped, never zeroed).
- `window.start`/`window.end`: min/max date present in the windowed token series; if the series is empty, `end = today.isoformat()` and `start = (today - timedelta(days=window_days - 1)).isoformat()`.
- `agents` (Ring), `skills`/`mcp` (Donuts), `heatmap` (Calendar): computed over **all** `valid_payloads` (lifetime), not the rolling window.
- `agents`: one entry per `SupportedAgent` in enum order, `tokens = aggregate_records(...)["agents"][name]["headline_total"]`.
- `skills`: `bucket_top_n(rank_usage(agg["skills"]), pie_top_n)`; `mcp`: same over `agg["mcp_servers"]`.
- `heatmap`: `daily_totals(valid_payloads)` → sorted `[{date, tokens}]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/render/test_dashboard_data.py
from datetime import date

from agent_usage.render.dashboard_data import build_dashboard_data

_STATUS = "available_with_activity"


def _agent(input_=0, output=0, reasoning=0, headline=0, sessions=0, status=_STATUS):
    return {
        "input_tokens": input_,
        "output_tokens": output,
        "reasoning_tokens": reasoning,
        "headline_total": headline,
        "session_count": sessions,
        "source_status": status,
    }


def _payload(day, *, device="dev1", claude=None, codex=None, skills=None, mcp=None):
    return {
        "schema_version": 1,
        "device_id": device,
        "date": day,
        "agents": {
            "claude_code": claude or _agent(status="source_unavailable"),
            "codex": codex or _agent(status="source_unavailable"),
            "hermes_agent": _agent(status="source_unavailable"),
        },
        "skills": skills or {},
        "mcp_servers": mcp or {},
        "mcp_tools": {},
    }


def test_build_dashboard_data_shapes_every_section():
    payloads = [
        _payload(
            "2026-07-10",
            claude=_agent(input_=100, output=50, reasoning=0, headline=150),
            skills={"brainstorming": 3, "tdd": 2, "graphify": 1},
            mcp={"gmail": 4, "calendar": 1},
        ),
        _payload(
            "2026-07-11",
            codex=_agent(input_=10, output=5, reasoning=2, headline=17),
        ),
    ]

    data = build_dashboard_data(payloads, today=date(2026, 7, 11), window_days=14, pie_top_n=2)

    assert data["window"] == {"start": "2026-07-10", "end": "2026-07-11"}
    assert data["tokens"] == [
        {"date": "2026-07-10", "input": 100, "output": 50, "reasoning": 0},
        {"date": "2026-07-11", "input": 10, "output": 5, "reasoning": 2},
    ]
    assert {"agent": "claude_code", "tokens": 150} in data["agents"]
    assert {"agent": "codex", "tokens": 17} in data["agents"]
    # pie_top_n=2 keeps top 2 skills and folds the rest into "Other"
    assert data["skills"] == [
        {"name": "brainstorming", "count": 3},
        {"name": "tdd", "count": 2},
        {"name": "Other", "count": 1},
    ]
    assert data["mcp"] == [{"name": "gmail", "count": 4}, {"name": "calendar", "count": 1}]
    assert data["heatmap"] == [
        {"date": "2026-07-10", "tokens": 150},
        {"date": "2026-07-11", "tokens": 17},
    ]


def test_build_dashboard_data_empty_uses_window_fallback():
    data = build_dashboard_data([], today=date(2026, 7, 18), window_days=14)
    assert data["window"] == {"start": "2026-07-05", "end": "2026-07-18"}
    assert data["tokens"] == []
    assert data["skills"] == []
    assert data["mcp"] == []
    assert data["heatmap"] == []
    assert all(entry["tokens"] == 0 for entry in data["agents"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/render/test_dashboard_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_usage.render.dashboard_data'`

- [ ] **Step 3: Implement the builder**

```python
# src/agent_usage/render/dashboard_data.py
"""Build the chart-ready ``data.json`` payload consumed by the interactive dashboard UI.

Pure and I/O-free: takes already-validated daily payloads (the same
``validate_and_partition(...).valid_payloads`` the Plotly path uses) and
reshapes them into the exact JSON contract the React charts expect.
"""

from __future__ import annotations

from datetime import date, timedelta

from agent_usage.aggregate import (
    aggregate_records,
    daily_token_totals,
    daily_totals,
    rolling_window,
)
from agent_usage.models import SupportedAgent
from agent_usage.render._counters import bucket_top_n, rank_usage


def _pie(counters: dict[str, int], pie_top_n: int) -> list[dict]:
    return [
        {"name": name, "count": count}
        for name, count in bucket_top_n(rank_usage(counters), pie_top_n)
    ]


def build_dashboard_data(
    valid_payloads: list[dict],
    *,
    today: date,
    window_days: int = 14,
    pie_top_n: int = 6,
) -> dict:
    """Reshape validated daily payloads into the dashboard's data.json contract."""
    windowed = rolling_window(valid_payloads, end=today, days=window_days)
    token_by_date = daily_token_totals(windowed)

    tokens = [
        {
            "date": day,
            "input": totals["input"],
            "output": totals["output"],
            "reasoning": totals["reasoning"],
        }
        for day, totals in sorted(token_by_date.items())
        if totals is not None
    ]

    if tokens:
        window = {"start": tokens[0]["date"], "end": tokens[-1]["date"]}
    else:
        start = today - timedelta(days=window_days - 1)
        window = {"start": start.isoformat(), "end": today.isoformat()}

    aggregated = aggregate_records(valid_payloads)
    agents = [
        {"agent": agent.value, "tokens": aggregated["agents"][agent.value]["headline_total"]}
        for agent in SupportedAgent
    ]

    heatmap = [
        {"date": day, "tokens": total}
        for day, total in sorted(daily_totals(valid_payloads).items())
    ]

    return {
        "window": window,
        "tokens": tokens,
        "agents": agents,
        "skills": _pie(aggregated["skills"], pie_top_n),
        "mcp": _pie(aggregated["mcp_servers"], pie_top_n),
        "heatmap": heatmap,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/render/test_dashboard_data.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/render/dashboard_data.py tests/render/test_dashboard_data.py
git commit -m "feat: add interactive dashboard data.json builder"
```

---

### Task 3: Shallow-clone helper for multi-device fetch

Add a shallow-clone helper to the existing git module and a small fetch function that clones the profile repo into a temp dir, reads `data/v1/devices/**`, and returns `(device_id, payload)` entries ready for `validate_and_partition`.

**Files:**
- Modify: `src/agent_usage/publish/git.py` (add `shallow_clone`)
- Create: `src/agent_usage/dashboard/__init__.py` (empty)
- Create: `src/agent_usage/dashboard/remote.py`
- Test: `tests/dashboard/test_remote.py`
- Create: `tests/dashboard/__init__.py` (empty, if the suite uses package dirs — mirror `tests/render/`)

**Interfaces:**
- Consumes: `agent_usage.publish.git._run` (module-internal), `GitCommandError`.
- Produces: `shallow_clone(repo_url: str, dest: Path, *, branch: str = "main") -> Path`; `fetch_device_entries(repo_target: str, *, branch: str = "main") -> list[tuple[str, dict]]` and exception `NoRepoTargetError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_remote.py
import json
from pathlib import Path

import pytest

from agent_usage.dashboard import remote


def test_fetch_device_entries_reads_cloned_device_payloads(monkeypatch, tmp_path):
    def fake_shallow_clone(repo_url, dest, *, branch="main"):
        devices = Path(dest) / "data" / "v1" / "devices" / "devA"
        devices.mkdir(parents=True)
        (devices / "2026-07-10.json").write_text(json.dumps({"date": "2026-07-10"}))
        (devices / "latest.json").write_text(json.dumps({"date": "2026-07-11"}))
        return Path(dest)

    monkeypatch.setattr(remote, "shallow_clone", fake_shallow_clone)

    entries = remote.fetch_device_entries("owner/repo")

    assert ("devA", {"date": "2026-07-10"}) in entries
    assert ("devA", {"date": "2026-07-11"}) in entries


def test_fetch_device_entries_requires_repo_target():
    with pytest.raises(remote.NoRepoTargetError):
        remote.fetch_device_entries(None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/dashboard/test_remote.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_usage.dashboard'`

- [ ] **Step 3: Add `shallow_clone` to `git.py`**

Append to `src/agent_usage/publish/git.py` (after `clone_or_open`):

```python
def shallow_clone(repo_url: str, dest: Path, *, branch: str = "main") -> Path:
    """Depth-1 single-branch clone of ``repo_url`` into a fresh ``dest`` directory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "clone",
        "--depth",
        "1",
        "--branch",
        branch,
        "--single-branch",
        repo_url,
        str(dest),
        cwd=dest.parent,
    )
    return dest
```

- [ ] **Step 4: Implement the remote fetch module**

```python
# src/agent_usage/dashboard/remote.py
"""Fetch multi-device published records by shallow-cloning the profile repo.

Used by ``agent-usage dashboard --all-devices``. Clones the configured
profile repository into a temporary directory, reads every device's public
daily records under ``data/v1/devices/**``, and returns them as
``(device_id, payload)`` entries for ``validate_and_partition``. The clone is
always removed afterward.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_usage.publish.git import shallow_clone

_DEVICES_SUBPATH = Path("data") / "v1" / "devices"


class NoRepoTargetError(Exception):
    """Raised when --all-devices is used but no profile repo target is configured."""


def _read_entries(devices_root: Path) -> list[tuple[str, dict]]:
    entries: list[tuple[str, dict]] = []
    if not devices_root.is_dir():
        return entries
    for device_dir in sorted(devices_root.iterdir()):
        if not device_dir.is_dir():
            continue
        device_id = device_dir.name
        for json_path in sorted(device_dir.glob("*.json")):
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            entries.append((device_id, payload))
    return entries


def fetch_device_entries(
    repo_target: str | None, *, branch: str = "main"
) -> list[tuple[str, dict]]:
    """Shallow-clone the profile repo and return every device's daily records."""
    if not repo_target:
        raise NoRepoTargetError(
            "no repo target set — run `agent-usage init --repo OWNER/REPO` first"
        )
    repo_url = f"https://github.com/{repo_target}.git"
    with tempfile.TemporaryDirectory(prefix="agent-usage-dash-") as tmp:
        clone_dir = Path(tmp) / "profile-repo"
        shallow_clone(repo_url, clone_dir, branch=branch)
        return _read_entries(clone_dir / _DEVICES_SUBPATH)
```

Note: `remote.py` imports `shallow_clone` by name so the test can `monkeypatch.setattr(remote, "shallow_clone", ...)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/dashboard/test_remote.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agent_usage/dashboard/__init__.py src/agent_usage/dashboard/remote.py \
        src/agent_usage/publish/git.py tests/dashboard/__init__.py tests/dashboard/test_remote.py
git commit -m "feat: fetch multi-device records via shallow clone for dashboard"
```

---

### Task 4: Payload assembly (local + remote → data.json dict)

A single entry point that produces the final `data.json` dict for either source, wiring the ledger/staging path (local) or the remote fetch (all-devices) into `validate_and_partition` + `build_dashboard_data`.

**Files:**
- Create: `src/agent_usage/dashboard/payload.py`
- Test: `tests/dashboard/test_payload.py`

**Interfaces:**
- Consumes: `agent_usage.ledger.repository.LedgerRepository`; `agent_usage.public_data.stage_daily_records`; `agent_usage.aggregate.validate_and_partition`; `agent_usage.render.dashboard_data.build_dashboard_data`; `agent_usage.dashboard.remote.fetch_device_entries`; `agent_usage.privacy.PrivacyPolicy`.
- Produces: `build_payload(*, ledger_path: Path, all_devices: bool, repo_target: str | None, privacy_policy: PrivacyPolicy, today: date, pie_top_n: int, tmp_stage_dir: Path) -> dict`.

Semantics:
- Local (`all_devices=False`): open ledger → `get_or_create_device_id` + `list_records` → `stage_daily_records(tmp_stage_dir, ...)` → `[(device_id, p) for p in payloads]`.
- Remote (`all_devices=True`): `fetch_device_entries(repo_target)`.
- Both: `validate_and_partition(entries, today=today).valid_payloads` → `build_dashboard_data(..., today=today, pie_top_n=pie_top_n)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_payload.py
from datetime import date

from agent_usage.dashboard import payload as payload_module


def test_build_payload_remote_uses_fetched_entries(monkeypatch, tmp_path):
    valid_entry = {
        "schema_version": 1,
        "device_id": "devA",
        "date": "2026-07-10",
        "agents": {},
        "skills": {},
        "mcp_servers": {},
        "mcp_tools": {},
    }
    captured = {}

    def fake_fetch(repo_target, *, branch="main"):
        captured["repo_target"] = repo_target
        return [("devA", valid_entry)]

    def fake_partition(entries, *, today):
        captured["entries"] = entries

        class R:
            valid_payloads = [valid_entry]

        return R()

    def fake_build(valid_payloads, *, today, pie_top_n):
        captured["valid_payloads"] = valid_payloads
        return {"ok": True}

    monkeypatch.setattr(payload_module, "fetch_device_entries", fake_fetch)
    monkeypatch.setattr(payload_module, "validate_and_partition", fake_partition)
    monkeypatch.setattr(payload_module, "build_dashboard_data", fake_build)

    result = payload_module.build_payload(
        ledger_path=tmp_path / "ledger.sqlite3",
        all_devices=True,
        repo_target="owner/repo",
        privacy_policy=payload_module.PrivacyPolicy(),
        today=date(2026, 7, 11),
        pie_top_n=6,
        tmp_stage_dir=tmp_path / "stage",
    )

    assert result == {"ok": True}
    assert captured["repo_target"] == "owner/repo"
    assert captured["valid_payloads"] == [valid_entry]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/dashboard/test_payload.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_usage.dashboard.payload'`

- [ ] **Step 3: Implement payload assembly**

```python
# src/agent_usage/dashboard/payload.py
"""Assemble the dashboard data.json from either local ledger data or multi-device data."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agent_usage.aggregate import validate_and_partition
from agent_usage.dashboard.remote import fetch_device_entries
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.privacy import PrivacyPolicy
from agent_usage.public_data import stage_daily_records
from agent_usage.render.dashboard_data import build_dashboard_data


def _local_entries(
    *, ledger_path: Path, privacy_policy: PrivacyPolicy, tmp_stage_dir: Path
) -> list[tuple[str, dict]]:
    repository = LedgerRepository.open(ledger_path)
    try:
        device_id = repository.get_or_create_device_id()
        records = repository.list_records()
    finally:
        repository.close()
    device_data_dir = tmp_stage_dir / "data" / "v1" / "devices" / device_id
    payloads = stage_daily_records(
        device_data_dir, device_id=device_id, records=records, privacy_policy=privacy_policy
    )
    return [(device_id, payload) for payload in payloads]


def build_payload(
    *,
    ledger_path: Path,
    all_devices: bool,
    repo_target: str | None,
    privacy_policy: PrivacyPolicy,
    today: date,
    pie_top_n: int,
    tmp_stage_dir: Path,
) -> dict:
    """Produce the dashboard data.json dict from the chosen data source."""
    if all_devices:
        entries = fetch_device_entries(repo_target)
    else:
        entries = _local_entries(
            ledger_path=ledger_path,
            privacy_policy=privacy_policy,
            tmp_stage_dir=tmp_stage_dir,
        )
    valid_payloads = validate_and_partition(entries, today=today).valid_payloads
    return build_dashboard_data(valid_payloads, today=today, pie_top_n=pie_top_n)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/dashboard/test_payload.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/dashboard/payload.py tests/dashboard/test_payload.py
git commit -m "feat: assemble dashboard payload from local or multi-device data"
```

---

### Task 5: Localhost HTTP server

A stdlib server that serves a UI `dist/` directory (produced on demand by Task 6) and injects `/data.json` from the in-memory payload. Binds `127.0.0.1`.

**Files:**
- Create: `src/agent_usage/dashboard/server.py`
- Test: `tests/dashboard/test_server.py`

**Interfaces:**
- Consumes: stdlib `http.server`, `socketserver`, `json`, `functools.partial`.
- Produces: `make_server(data: dict, *, dist_dir: Path, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer`; `serve(data, *, dist_dir, host="127.0.0.1", port=8000, open_browser=True) -> None`.

Semantics: `GET /data.json` returns the JSON payload with `Content-Type: application/json`; any other path is served as a static file from `dist_dir` (SPA: a missing file falls back to `index.html`). `make_server` returns an unstarted server (testable); `serve` opens the browser (unless disabled) and calls `serve_forever`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_server.py
import json
import urllib.request
from pathlib import Path
from threading import Thread

from agent_usage.dashboard.server import make_server


def _get(url: str) -> tuple[int, bytes, str]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, resp.read(), resp.headers.get("Content-Type", "")


def test_server_serves_index_and_injects_data_json(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>dash</title>", encoding="utf-8")

    data = {"window": {"start": "2026-07-10", "end": "2026-07-11"}, "tokens": []}
    server = make_server(data, dist_dir=dist, port=0)
    host, port = server.server_address
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, body, _ = _get(f"{base}/index.html")
        assert status == 200
        assert b"dash" in body

        status, body, ctype = _get(f"{base}/data.json")
        assert status == 200
        assert ctype.startswith("application/json")
        assert json.loads(body) == data
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_binds_loopback_only(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("x", encoding="utf-8")
    server = make_server({}, dist_dir=dist, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/dashboard/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_usage.dashboard.server'`

- [ ] **Step 3: Implement the server**

```python
# src/agent_usage/dashboard/server.py
"""Serve the interactive dashboard on localhost: committed dist/ plus injected data.json."""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, data_bytes: bytes, dist_dir: Path, **kwargs) -> None:
        self._data_bytes = data_bytes
        super().__init__(*args, directory=str(dist_dir), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.split("?", 1)[0] == "/data.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(self._data_bytes)))
            self.end_headers()
            self.wfile.write(self._data_bytes)
            return
        super().do_GET()

    def send_head(self):  # SPA fallback: unknown path -> index.html
        path = self.translate_path(self.path)
        if not Path(path).exists() and "." not in Path(self.path).name:
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


def make_server(
    data: dict, *, dist_dir: Path, host: str = "127.0.0.1", port: int = 8000
) -> ThreadingHTTPServer:
    """Build (but do not start) the localhost dashboard server."""
    handler = partial(
        _DashboardHandler,
        data_bytes=json.dumps(data).encode("utf-8"),
        dist_dir=dist_dir,
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    data: dict,
    *,
    dist_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
) -> None:
    """Serve the dashboard until interrupted (Ctrl-C)."""
    server = make_server(data, dist_dir=dist_dir, host=host, port=port)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"
    print(f"agent-usage: dashboard serving at {url} (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/dashboard/test_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/dashboard/server.py tests/dashboard/test_server.py
git commit -m "feat: add localhost dashboard http server"
```

---

### Task 6: On-demand UI build orchestration

Build the React UI when the command runs, caching the result and rebuilding only when the UI source is newer than the last build. Returns the servable `dist/` directory. All subprocess calls go through an injectable `run` so the logic is unit-testable without Node.

**Files:**
- Create: `src/agent_usage/dashboard/ui_build.py`
- Test: `tests/dashboard/test_ui_build.py`

**Interfaces:**
- Consumes: stdlib `shutil.which`, `subprocess.run`.
- Produces: `ensure_build(ui_dir: Path, *, force: bool = False, run=subprocess.run) -> Path` (returns `ui_dir / "dist"`); exception `UIBuildError`.

Semantics:
- Fresh (not `force`, `dist/index.html` exists and is newer than every UI source file under `src/` plus `package.json`/`vite.config.ts`/`index.html`): return `dist/` without building.
- Otherwise: pick `pnpm` then `npm` via `shutil.which` (raise `UIBuildError` if neither); run `<pm> install` when `node_modules/` is absent; run `<pm> build`; raise `UIBuildError` on any non-zero exit or if `dist/index.html` is still missing.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_ui_build.py
from pathlib import Path

import pytest

from agent_usage.dashboard import ui_build


def test_ensure_build_skips_when_fresh(tmp_path):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("x", encoding="utf-8")
    calls = []

    result = ui_build.ensure_build(tmp_path, run=lambda *a, **k: calls.append(a))

    assert result == tmp_path / "dist"
    assert calls == []


def test_ensure_build_runs_install_and_build_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_build, "_package_manager", lambda: ["pnpm"])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("x", encoding="utf-8")
    ran = []

    def fake_run(cmd, *, cwd, capture_output, text):
        ran.append(cmd)
        if cmd[-1] == "build":
            dist = Path(cwd) / "dist"
            dist.mkdir(exist_ok=True)
            (dist / "index.html").write_text("y", encoding="utf-8")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    result = ui_build.ensure_build(tmp_path, run=fake_run)

    assert (result / "index.html").is_file()
    assert ["pnpm", "install"] in ran
    assert ["pnpm", "build"] in ran


def test_ensure_build_raises_on_build_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_build, "_package_manager", lambda: ["npm"])
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("x", encoding="utf-8")

    def fake_run(cmd, *, cwd, capture_output, text):
        class Result:
            returncode = 1
            stderr = "boom"

        return Result()

    with pytest.raises(ui_build.UIBuildError):
        ui_build.ensure_build(tmp_path, run=fake_run)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/dashboard/test_ui_build.py -v`
Expected: FAIL with `ImportError: cannot import name 'ui_build'` (module missing)

- [ ] **Step 3: Implement the build orchestrator**

```python
# src/agent_usage/dashboard/ui_build.py
"""Build the React dashboard UI on demand and return the servable dist directory.

Called each time ``agent-usage dashboard`` runs. The build is cached: if
``dist/index.html`` is newer than every UI source file, it is reused as-is.
Otherwise the UI is rebuilt with pnpm (or npm). No build artifact is ever
committed — ``dist/`` is a local, gitignored cache.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

_ROOT_SOURCES = ("package.json", "vite.config.ts", "index.html")


class UIBuildError(Exception):
    """A user-facing failure while building the dashboard UI."""


def _package_manager() -> list[str]:
    for manager in ("pnpm", "npm"):
        if shutil.which(manager):
            return [manager]
    raise UIBuildError(
        "Node package manager not found — install Node.js and pnpm (or npm) "
        "to build the dashboard UI"
    )


def _source_files(ui_dir: Path) -> Iterator[Path]:
    src = ui_dir / "src"
    if src.is_dir():
        yield from (path for path in src.rglob("*") if path.is_file())
    for name in _ROOT_SOURCES:
        candidate = ui_dir / name
        if candidate.is_file():
            yield candidate


def _is_stale(ui_dir: Path, dist_dir: Path) -> bool:
    index = dist_dir / "index.html"
    if not index.is_file():
        return True
    built_at = index.stat().st_mtime
    return any(source.stat().st_mtime > built_at for source in _source_files(ui_dir))


def _run_step(run, command: list[str], cwd: Path) -> None:
    result = run(command, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise UIBuildError(f"`{' '.join(command)}` failed:\n{result.stderr}")


def ensure_build(ui_dir: Path, *, force: bool = False, run=subprocess.run) -> Path:
    """Ensure the UI is built and return its dist directory, rebuilding only if needed."""
    dist_dir = ui_dir / "dist"
    if not force and not _is_stale(ui_dir, dist_dir):
        return dist_dir
    package_manager = _package_manager()
    if not (ui_dir / "node_modules").is_dir():
        _run_step(run, [*package_manager, "install"], ui_dir)
    _run_step(run, [*package_manager, "build"], ui_dir)
    if not (dist_dir / "index.html").is_file():
        raise UIBuildError("dashboard UI build did not produce dist/index.html")
    return dist_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/dashboard/test_ui_build.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/dashboard/ui_build.py tests/dashboard/test_ui_build.py
git commit -m "feat: build dashboard UI on demand with caching"
```

---

### Task 7: CLI command wiring

Add the `dashboard` Typer command: resolve config, build the payload, build the UI on demand (Task 6), and serve.

**Files:**
- Create: `src/agent_usage/commands/dashboard.py`
- Modify: `src/agent_usage/cli.py` (import + `@app.command()` def)
- Test: `tests/commands/test_dashboard_cli.py` (mirror existing `tests/commands/` layout; add `tests/commands/__init__.py` only if that dir uses one)

**Interfaces:**
- Consumes: `agent_usage.dashboard.payload.build_payload`; `agent_usage.dashboard.ui_build.{ensure_build, UIBuildError}`; `agent_usage.dashboard.server.serve`; `agent_usage.dashboard.remote.NoRepoTargetError`; `agent_usage.config.{load_config, config_file_path, ledger_file_path}`; `agent_usage.privacy.PrivacyPolicy`.
- Produces: `commands/dashboard.py::run(*, ledger_path, config_path, all_devices, port, open_browser, pie_top_n, ui_dir, force_build, today, tmp_stage_dir) -> None`; a `UI_DIR` module constant resolving the repo's `dashboard-ui/` source directory.

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_dashboard_cli.py
from datetime import date

import pytest

from agent_usage.commands import dashboard as dashboard_command
from agent_usage.dashboard.remote import NoRepoTargetError


def test_run_builds_payload_and_serves(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setattr(
        dashboard_command, "build_payload", lambda **kwargs: {"served": kwargs["all_devices"]}
    )
    monkeypatch.setattr(
        dashboard_command, "ensure_build", lambda ui_dir, *, force: ui_dir / "dist"
    )

    def fake_serve(data, *, dist_dir, port, open_browser):
        calls["data"] = data
        calls["dist_dir"] = dist_dir
        calls["port"] = port
        calls["open_browser"] = open_browser

    monkeypatch.setattr(dashboard_command, "serve", fake_serve)

    dashboard_command.run(
        ledger_path=tmp_path / "ledger.sqlite3",
        config_path=tmp_path / "config.json",
        all_devices=True,
        port=8123,
        open_browser=False,
        pie_top_n=6,
        ui_dir=tmp_path / "dashboard-ui",
        force_build=False,
        today=date(2026, 7, 18),
        tmp_stage_dir=tmp_path / "stage",
    )

    assert calls["data"] == {"served": True}
    assert calls["dist_dir"] == tmp_path / "dashboard-ui" / "dist"
    assert calls["port"] == 8123
    assert calls["open_browser"] is False


def test_run_reports_missing_repo_target(monkeypatch, tmp_path):
    def boom(**kwargs):
        raise NoRepoTargetError("no repo target set")

    monkeypatch.setattr(dashboard_command, "build_payload", boom)
    monkeypatch.setattr(dashboard_command, "ensure_build", lambda ui_dir, *, force: ui_dir)
    monkeypatch.setattr(dashboard_command, "serve", lambda *a, **k: None)

    with pytest.raises(dashboard_command.DashboardError):
        dashboard_command.run(
            ledger_path=tmp_path / "ledger.sqlite3",
            config_path=tmp_path / "config.json",
            all_devices=True,
            port=8000,
            open_browser=False,
            pie_top_n=6,
            ui_dir=tmp_path / "dashboard-ui",
            force_build=False,
            today=date(2026, 7, 18),
            tmp_stage_dir=tmp_path / "stage",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_dashboard_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_usage.commands.dashboard'`

- [ ] **Step 3: Implement the command module**

```python
# src/agent_usage/commands/dashboard.py
"""`agent-usage dashboard`: build the payload and serve the interactive localhost dashboard."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agent_usage.config import load_config
from agent_usage.dashboard.payload import build_payload
from agent_usage.dashboard.remote import NoRepoTargetError
from agent_usage.dashboard.server import serve
from agent_usage.dashboard.ui_build import UIBuildError, ensure_build
from agent_usage.privacy import PrivacyPolicy

# The React UI source lives at the repo root under dashboard-ui/.
# commands/dashboard.py -> commands -> agent_usage -> src -> <repo root>.
UI_DIR = Path(__file__).resolve().parents[3] / "dashboard-ui"


class DashboardError(Exception):
    """A user-facing dashboard failure (surfaced by the CLI as a clean message)."""


def run(
    *,
    ledger_path: Path,
    config_path: Path,
    all_devices: bool,
    port: int,
    open_browser: bool,
    pie_top_n: int,
    ui_dir: Path,
    force_build: bool,
    today: date,
    tmp_stage_dir: Path,
) -> None:
    """Build the payload, build the UI on demand, and serve until interrupted."""
    config = load_config(config_path)
    try:
        data = build_payload(
            ledger_path=ledger_path,
            all_devices=all_devices,
            repo_target=config.repo_target,
            privacy_policy=PrivacyPolicy.from_config(config),
            today=today,
            pie_top_n=pie_top_n,
            tmp_stage_dir=tmp_stage_dir,
        )
    except NoRepoTargetError as error:
        raise DashboardError(str(error)) from error

    if not ui_dir.is_dir():
        raise DashboardError(
            f"dashboard UI source not found at {ui_dir} — run from a repository checkout"
        )
    try:
        dist_dir = ensure_build(ui_dir, force=force_build)
    except UIBuildError as error:
        raise DashboardError(str(error)) from error

    serve(data, dist_dir=dist_dir, port=port, open_browser=open_browser)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_dashboard_cli.py -v`
Expected: PASS

- [ ] **Step 5: Wire the command into `cli.py`**

Add to the imports block in `src/agent_usage/cli.py`:

```python
from agent_usage.commands import dashboard as dashboard_command
```

Add this command (after the `render` command), using a temp stage dir so the local path never writes into the user's tree:

```python
@app.command()
def dashboard(
    all_devices: bool = typer.Option(
        False, "--all-devices", help="Aggregate multi-device data cloned from the profile repo."
    ),
    port: int = typer.Option(8000, "--port", help="Localhost port to serve on."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open a browser automatically."),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Force a fresh UI build even if the cached build looks current."
    ),
    pie_top_n: int = typer.Option(
        6, "--pie-top-n", help="Max Skills/MCP pie slices before bucketing the rest into 'Other'."
    ),
) -> None:
    """Serve an interactive localhost usage dashboard (local data, or --all-devices)."""
    if pie_top_n < 1:
        raise typer.BadParameter("--pie-top-n must be at least 1")
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="agent-usage-dash-") as tmp:
        try:
            dashboard_command.run(
                ledger_path=ledger_file_path(),
                config_path=config_file_path(),
                all_devices=all_devices,
                port=port,
                open_browser=not no_open,
                pie_top_n=pie_top_n,
                ui_dir=dashboard_command.UI_DIR,
                force_build=rebuild,
                today=now.date(),
                tmp_stage_dir=Path(tmp),
            )
        except dashboard_command.DashboardError as error:
            typer.echo(f"agent-usage: {error}")
            raise typer.Exit(code=1) from error
```

Add `import tempfile` to the top of `cli.py` (alongside `import sys`).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (all tests, no regressions)

- [ ] **Step 7: Commit**

```bash
git add src/agent_usage/commands/dashboard.py src/agent_usage/cli.py tests/commands/test_dashboard_cli.py
git commit -m "feat: add agent-usage dashboard command"
```

---

### Task 8: React + bklit UI source (built on demand)

Scaffold the Vite + React + bklit app under `dashboard-ui/` and implement the five chart blocks against the `data.json` contract in the required dark theme. Do **not** build or commit a `dist/` — Task 6's `ensure_build` compiles it on demand when the command runs, and `dashboard-ui/dist/` stays gitignored.

This task is not Python-TDD; verification is manual (`agent-usage dashboard` builds the UI and renders). Do not run a Node build in CI.

**Files:**
- Create: `dashboard-ui/` (Vite React scaffold: `package.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/theme.css`, chart components under `src/charts/`)
- Create: `dashboard-ui/README.md` (how to develop the UI; note the CLI builds it automatically)
- Modify: `.gitignore` (ignore `dashboard-ui/node_modules/` and `dashboard-ui/dist/`)

**Interfaces:**
- Consumes: `GET /data.json` matching the Global Constraints contract.
- Produces: buildable UI source whose `pnpm build` (or `npm run build`) emits `dashboard-ui/dist/index.html` — the directory Task 6 returns and Task 5 serves.

- [ ] **Step 1: Scaffold the Vite React + TypeScript app**

```bash
cd dashboard-ui
pnpm create vite@latest . --template react-ts
pnpm install
```

Set `vite.config.ts` to emit relative asset paths (served from the package root) — add `base: "./"` and `build.outDir: "dist"`:

```ts
// dashboard-ui/vite.config.ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist" },
});
```

- [ ] **Step 2: Add bklit chart components and peer deps**

```bash
cd dashboard-ui
pnpm dlx shadcn@latest add @bklit/area-chart @bklit/ring-chart @bklit/pie-chart @bklit/heatmap-chart
pnpm add @visx/shape @visx/curve @visx/scale @visx/gradient @visx/responsive @visx/event @visx/grid d3-array motion react-use-measure
```

If bklit's heatmap-chart cannot render a GitHub-contributions calendar (X = weeks, Y = day-of-week, one cell per day, intensity = total tokens), build a small custom `CalendarHeatmap` component instead (plain divs / SVG grid) styled to the theme below. Decide by trying the bklit component first.

- [ ] **Step 3: Define the theme (hard color constraints)**

```css
/* dashboard-ui/src/theme.css */
:root {
  --page-bg: #090A0B;
  --block-bg: #0E0F13;
}
html, body, #root { margin: 0; background: var(--page-bg); color: #E5E7EB; }
body { font-family: ui-sans-serif, system-ui, sans-serif; }

.dashboard { max-width: 1100px; margin: 0 auto; padding: 24px; display: grid; gap: 16px; }
.block {
  background: var(--block-bg);   /* flat fill — never a gradient */
  border-radius: 12px;
  padding: 16px 20px;
}
.block h2 { margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #9CA3AF; }
.row-two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 720px) { .row-two { grid-template-columns: 1fr; } }
```

Constraint reminder: `background` on `.block` and the page MUST be flat hex fills. Do NOT introduce `linear-gradient`/`radial-gradient` on any page or block element. Gradients internal to a bklit chart's own default rendering are allowed and must be left intact.

- [ ] **Step 4: Fetch `data.json` and render the five blocks**

```tsx
// dashboard-ui/src/App.tsx
import { useEffect, useState } from "react";
import "./theme.css";
import { TokenArea } from "./charts/TokenArea";
import { AgentRing } from "./charts/AgentRing";
import { UsageDonut } from "./charts/UsageDonut";
import { CalendarHeatmap } from "./charts/CalendarHeatmap";

type Data = {
  window: { start: string; end: string };
  tokens: { date: string; input: number; output: number; reasoning: number }[];
  agents: { agent: string; tokens: number }[];
  skills: { name: string; count: number }[];
  mcp: { name: string; count: number }[];
  heatmap: { date: string; tokens: number }[];
};

export default function App() {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => {
    fetch("/data.json").then((r) => r.json()).then(setData);
  }, []);
  if (!data) return <div className="dashboard">Loading…</div>;
  return (
    <div className="dashboard">
      <section className="block">
        <h2>Total Token Usage</h2>
        <TokenArea data={data.tokens} />
      </section>
      <section className="block">
        <h2>Usage by Agent</h2>
        <AgentRing data={data.agents} />
      </section>
      <div className="row-two">
        <section className="block">
          <h2>Skill Usage</h2>
          <UsageDonut data={data.skills} />
        </section>
        <section className="block">
          <h2>MCP Usage</h2>
          <UsageDonut data={data.mcp} />
        </section>
      </div>
      <section className="block">
        <h2>Activity</h2>
        <CalendarHeatmap data={data.heatmap} />
      </section>
    </div>
  );
}
```

Implement each chart component under `dashboard-ui/src/charts/` using the corresponding bklit component and the minimal API from the bklit docs:
- `TokenArea`: area-chart with `input`/`output`/`reasoning` series over `date`. Agent display names: map `hermes_agent`→"Hermes", `claude_code`→"Claude Code", `codex`→"Codex".
- `AgentRing`: ring-chart of `agents` by `tokens`, using the same display-name map.
- `UsageDonut`: pie-chart with an inner radius (donut) over `{name, count}`.
- `CalendarHeatmap`: GitHub-contributions calendar over `{date, tokens}` (X=weeks, Y=day-of-week, grayscale Less→More).

- [ ] **Step 5: Ignore build artifacts (do not commit `dist/`)**

In `.gitignore`, add:

```gitignore
dashboard-ui/node_modules/
dashboard-ui/dist/
```

No `dist/` is committed and no `pyproject.toml` packaging change is needed — the CLI builds `dashboard-ui/dist/` on demand at run time and serves it from the checkout.

- [ ] **Step 6: Verify the on-demand build produces `dist/index.html`**

```bash
cd dashboard-ui
pnpm install
pnpm build          # emits dashboard-ui/dist/index.html
ls dist/index.html
```

This confirms the source compiles. The CLI (Task 6's `ensure_build`) runs these same steps automatically; this manual run just validates the scaffold once.

- [ ] **Step 7: Manual verification through the CLI (on-demand build path)**

```bash
rm -rf dashboard-ui/dist          # prove the CLI builds from scratch
uv run agent-usage collect        # ensure some local data exists
uv run agent-usage dashboard --no-open --port 8000
# The command should build the UI (pnpm install/build) then start serving.
# In another shell:
curl -s http://127.0.0.1:8000/data.json | head -c 200
# Open http://127.0.0.1:8000 in a browser: confirm the charts load after the
# page fetches /data.json, all 5 blocks render, page bg is #090A0B, blocks are
# #0E0F13, and no gradient backgrounds appear (only bklit's own in-chart gradients).
```

Then verify multi-device:

```bash
uv run agent-usage dashboard --all-devices --no-open
```

- [ ] **Step 8: Commit**

```bash
git add dashboard-ui .gitignore
git commit -m "feat: add React + bklit interactive dashboard UI (built on demand)"
```

---

## Self-Review Notes

- **Spec coverage:** local default (Tasks 4, 7) · `--all-devices` git clone (Tasks 3, 4) · data.json contract (Task 2) · localhost server binding loopback (Task 5) · on-demand UI build, no committed bundle (Tasks 6, 8) · client fetches `/data.json` on page open (Task 8 `App.tsx`) · CLI flags `--all-devices/--port/--no-open/--rebuild/--pie-top-n` (Task 7) · 5 chart blocks + theme + no-gradient rule (Task 8) · Plotly path untouched (Task 1 re-exports) · lifetime vs rolling-window semantics (Task 2). All covered.
- **Heatmap open risk** (spec) is carried into Task 8 Step 2 with a concrete fallback.
- **Type consistency:** `build_dashboard_data`, `build_payload`, `fetch_device_entries`, `shallow_clone`, `make_server`/`serve`, `ensure_build`/`UIBuildError`, `run`/`UI_DIR`/`DashboardError` names are used identically across producing and consuming tasks.
