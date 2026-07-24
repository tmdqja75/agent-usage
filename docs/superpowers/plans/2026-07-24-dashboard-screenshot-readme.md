# Dashboard Screenshot README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the five Plotly PNG charts in the managed README section with a single full-page Playwright screenshot of the real React dashboard, for both local `render` and the profile-repo CI.

**Architecture:** A new `dashboard/export.py` reuses the existing `build_payload` + `ensure_build` + `make_server` pieces, starts a short-lived loopback server on an ephemeral port, drives headless Chromium (dark, reduced-motion, 2s settle) and writes one `dashboard.png`. `render.py`, `markdown.py`, and the CI script/workflow are rewired to this path; Plotly and Kaleido are removed.

**Tech Stack:** Python 3.11, Typer, Playwright (sync API) + Chromium, Vite/React (`dashboard-ui/`), pytest.

## Global Constraints

- `requires-python >= 3.11`.
- macOS-first for the local CLI; the CI Action runs on `ubuntu-latest`.
- Export server MUST bind `127.0.0.1` on an OS-selected ephemeral port (`port=0`) and MUST always be shut down in a `finally` block.
- Export browser context MUST use `color_scheme="dark"`, `reduced_motion="reduce"`, `device_scale_factor=2`, viewport width `1100`.
- Fixed animation settle wait is exactly `2000` ms (`page.wait_for_timeout(2000)`). Never replace with an unbounded wait.
- Export network route MUST allow only `http://127.0.0.1:{port}/`-prefixed URLs; all other requests aborted.
- Single README asset path: `assets/agent-usage/dashboard.png`.
- Managed README markers unchanged: `<!-- agent-usage:start -->` / `<!-- agent-usage:end -->`.

---

### Task 1: Swap dependencies (remove Plotly/Kaleido, add Playwright)

**Files:**
- Modify: `pyproject.toml:18-23` (`dependencies` array)

**Interfaces:**
- Consumes: nothing.
- Produces: `playwright` importable; `plotly`/`kaleido` no longer required.

- [ ] **Step 1: Edit dependencies**

In `pyproject.toml`, replace the `dependencies` block:

```toml
dependencies = [
    "platformdirs>=4.10.1",
    "playwright>=1.44",
    "typer>=0.12",
]
```

(Remove `kaleido==0.2.1` and `plotly>=5.24,<6`.)

- [ ] **Step 2: Sync and install the browser**

Run:
```bash
uv sync --dev
uv run python -m playwright install chromium
```
Expected: sync resolves without plotly/kaleido; Chromium downloads successfully.

- [ ] **Step 3: Verify import**

Run:
```bash
uv run python -c "import playwright.sync_api; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: replace plotly/kaleido with playwright"
```

---

### Task 2: `dashboard/export.py` — screenshot export module

**Files:**
- Create: `src/agent_usage/dashboard/export.py`
- Test: `tests/dashboard/test_export.py`

**Interfaces:**
- Consumes: `dashboard.payload.build_payload`, `dashboard.ui_build.ensure_build`, `dashboard.server.make_server`, `privacy.PrivacyPolicy`.
- Produces:
  - `_url_allowed(url: str, prefix: str) -> bool`
  - `_launch_chromium(playwright, *, installer=subprocess.run)` — returns a launched `Browser`, auto-installing Chromium once on a missing-executable error.
  - `screenshot_payload(payload: dict, output_path: Path, *, dist_dir: Path, lang: str = "en", width: int = 1100, scale: int = 2) -> None` — the browser core; screenshots an already-assembled payload against an already-built dist. This is what CI (local data) and the local wrapper both funnel through.
  - `export_dashboard_png(output_path: Path, *, ledger_path: Path, all_devices: bool, repo_target: str | None, privacy_policy: PrivacyPolicy, today: date, ui_dir: Path, tmp_stage_dir: Path, lang: str = "en", pie_top_n: int = 6, width: int = 1100, scale: int = 2, force_build: bool = False) -> None` — local convenience wrapper: `build_payload` → `ensure_build` → `screenshot_payload`.

- [ ] **Step 1: Write failing tests for the pure helpers**

Create `tests/dashboard/test_export.py`:

```python
import subprocess
from types import SimpleNamespace

import pytest

from agent_usage.dashboard import export


def test_url_allowed_accepts_matching_prefix():
    prefix = "http://127.0.0.1:54321/"
    assert export._url_allowed("http://127.0.0.1:54321/data.json", prefix)
    assert export._url_allowed("http://127.0.0.1:54321/", prefix)


def test_url_allowed_rejects_foreign_host():
    prefix = "http://127.0.0.1:54321/"
    assert not export._url_allowed("https://example.com/x.js", prefix)
    assert not export._url_allowed("http://127.0.0.1:9999/x", prefix)


def test_launch_chromium_installs_once_on_missing_executable():
    calls = {"launch": 0, "install": []}

    class FakeChromium:
        def launch(self, *, headless):
            calls["launch"] += 1
            if calls["launch"] == 1:
                raise RuntimeError("Executable doesn't exist at /x/chromium")
            return SimpleNamespace(name="browser")

    def fake_installer(cmd, **kwargs):
        calls["install"].append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    pw = SimpleNamespace(chromium=FakeChromium())
    browser = export._launch_chromium(pw, installer=fake_installer)

    assert browser.name == "browser"
    assert calls["launch"] == 2
    assert calls["install"] and "install" in calls["install"][0]
    assert "chromium" in calls["install"][0]


def test_launch_chromium_reraises_unrelated_error():
    class FakeChromium:
        def launch(self, *, headless):
            raise RuntimeError("some other failure")

    pw = SimpleNamespace(chromium=FakeChromium())
    with pytest.raises(RuntimeError, match="some other failure"):
        export._launch_chromium(pw, installer=lambda *a, **k: None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/dashboard/test_export.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` (module/functions not defined).

- [ ] **Step 3: Implement `export.py`**

Create `src/agent_usage/dashboard/export.py`:

```python
"""Capture the interactive React dashboard as a single PNG via headless Chromium.

Reuses the same payload, UI build, and loopback server the interactive
``dashboard`` command uses, then drives Playwright/Chromium to screenshot the
fully rendered page. Everything is local: an ephemeral loopback server, a
route allow-list that blocks any non-loopback request, and a server that is
always shut down in a ``finally`` block.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from agent_usage.dashboard.payload import build_payload
from agent_usage.dashboard.server import make_server
from agent_usage.dashboard.ui_build import ensure_build
from agent_usage.privacy import PrivacyPolicy

_SETTLE_MS = 2000
_MISSING_BROWSER_HINTS = ("Executable doesn't exist", "playwright install")


def _url_allowed(url: str, prefix: str) -> bool:
    """True only for URLs served by our own loopback server."""
    return url.startswith(prefix)


def _launch_chromium(playwright, *, installer=subprocess.run):
    """Launch headless Chromium, auto-installing it once if the binary is missing."""
    try:
        return playwright.chromium.launch(headless=True)
    except (PlaywrightError, RuntimeError) as error:
        message = str(error)
        if not any(hint in message for hint in _MISSING_BROWSER_HINTS):
            raise
        result = installer(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
        )
        if getattr(result, "returncode", 0) != 0:
            raise RuntimeError(
                "failed to install Chromium for dashboard export — run "
                "`playwright install chromium` manually"
            ) from error
        return playwright.chromium.launch(headless=True)


def screenshot_payload(
    payload: dict,
    output_path: Path,
    *,
    dist_dir: Path,
    lang: str = "en",
    width: int = 1100,
    scale: int = 2,
) -> None:
    """Screenshot an already-assembled payload against an already-built dist."""
    server = make_server(payload, dist_dir=dist_dir, host="127.0.0.1", port=0, lang=lang)
    port = server.server_address[1]
    prefix = f"http://127.0.0.1:{port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium(playwright)
            context = browser.new_context(
                viewport={"width": width, "height": 900},
                device_scale_factor=scale,
                color_scheme="dark",
                reduced_motion="reduce",
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if _url_allowed(route.request.url, prefix)
                    else route.abort()
                ),
            )
            page = context.new_page()
            page.goto(prefix, wait_until="networkidle")
            page.wait_for_function(
                "document.querySelector('.dashboard')"
                " && !document.body.innerText.includes('Loading…')"
            )
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(_SETTLE_MS)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output_path), full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def export_dashboard_png(
    output_path: Path,
    *,
    ledger_path: Path,
    all_devices: bool,
    repo_target: str | None,
    privacy_policy: PrivacyPolicy,
    today: date,
    ui_dir: Path,
    tmp_stage_dir: Path,
    lang: str = "en",
    pie_top_n: int = 6,
    width: int = 1100,
    scale: int = 2,
    force_build: bool = False,
) -> None:
    """Assemble the local payload, build the UI, and screenshot it to ``output_path``."""
    payload = build_payload(
        ledger_path=ledger_path,
        all_devices=all_devices,
        repo_target=repo_target,
        privacy_policy=privacy_policy,
        today=today,
        pie_top_n=pie_top_n,
        tmp_stage_dir=tmp_stage_dir,
    )
    dist_dir = ensure_build(ui_dir, force=force_build)
    screenshot_payload(
        payload, output_path, dist_dir=dist_dir, lang=lang, width=width, scale=scale
    )
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `uv run pytest tests/dashboard/test_export.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Add a gated integration test**

Append to `tests/dashboard/test_export.py`:

```python
def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            b.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_available(), reason="Chromium not installed")
def test_export_writes_png(tmp_path):
    from datetime import date as _date
    from pathlib import Path

    from agent_usage.privacy import PrivacyPolicy

    repo_root = Path(__file__).resolve().parents[2]
    out = tmp_path / "dashboard.png"
    ledger = tmp_path / "ledger.sqlite3"

    export.export_dashboard_png(
        out,
        ledger_path=ledger,
        all_devices=False,
        repo_target=None,
        privacy_policy=PrivacyPolicy(),
        today=_date(2026, 7, 24),
        ui_dir=repo_root / "dashboard-ui",
        tmp_stage_dir=tmp_path / "stage",
    )

    assert out.is_file()
    assert out.stat().st_size > 0
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 6: Run the integration test**

Run: `uv run pytest tests/dashboard/test_export.py -v`
Expected: PASS, or `test_export_writes_png` SKIPPED if Chromium/Node unavailable. (Requires `dashboard-ui` build deps; skip is acceptable in constrained environments.)

- [ ] **Step 7: Commit**

```bash
git add src/agent_usage/dashboard/export.py tests/dashboard/test_export.py
git commit -m "feat(dashboard): add playwright screenshot export"
```

---

### Task 3: Screenshot-only README markdown section

**Files:**
- Modify: `src/agent_usage/render/markdown.py` (remove chart params, `render_dashboard`, plotly import; add screenshot section)
- Test: `tests/render/test_markdown.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `DASHBOARD_IMAGE_PATH = "assets/agent-usage/dashboard.png"`
  - `render_dashboard_markdown(*, image_path: str = DASHBOARD_IMAGE_PATH) -> str`
  - `update_readme(existing_readme: str, dashboard_markdown: str) -> str` (unchanged)
  - `render_dashboard` REMOVED.

- [ ] **Step 1: Write the failing test**

Replace the body of `tests/render/test_markdown.py` with tests for the new section (keep any `update_readme` idempotence tests, adapting to the new content):

```python
from agent_usage.render.markdown import (
    DASHBOARD_IMAGE_PATH,
    MARKER_END,
    MARKER_START,
    render_dashboard_markdown,
    update_readme,
)


def test_section_contains_single_screenshot_reference():
    md = render_dashboard_markdown()
    assert MARKER_START in md and MARKER_END in md
    assert f"]({DASHBOARD_IMAGE_PATH})" in md
    # No leftover per-chart images.
    for stale in ("token-activity-14d.png", "agent-share.png", "skills.png", "mcp.png"):
        assert stale not in md


def test_section_uses_custom_image_path():
    md = render_dashboard_markdown(image_path="x/y/dash.png")
    assert "](x/y/dash.png)" in md


def test_update_readme_replaces_between_markers_and_is_idempotent():
    existing = "# Title\n\nintro\n\n<!-- agent-usage:start -->\nOLD\n<!-- agent-usage:end -->\n\nfooter\n"
    section = render_dashboard_markdown()
    once = update_readme(existing, section)
    twice = update_readme(once, section)
    assert once == twice
    assert "# Title" in once and "footer" in once
    assert "OLD" not in once
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/render/test_markdown.py -v`
Expected: FAIL (`ImportError` for `DASHBOARD_IMAGE_PATH`, or old signature).

- [ ] **Step 3: Rewrite `markdown.py`**

Replace the plotly import and the chart-path constants/functions. New relevant parts:

```python
from __future__ import annotations

MARKER_START = "<!-- agent-usage:start -->"
MARKER_END = "<!-- agent-usage:end -->"

DASHBOARD_IMAGE_PATH = "assets/agent-usage/dashboard.png"


def render_dashboard_markdown(*, image_path: str = DASHBOARD_IMAGE_PATH) -> str:
    """Render the managed dashboard section: a single dashboard screenshot."""
    sections = [
        MARKER_START,
        "## Agent Usage",
        "",
        f"![Agent Usage dashboard]({image_path})",
        "",
        MARKER_END,
    ]
    return "\n".join(sections)


def update_readme(existing_readme: str, dashboard_markdown: str) -> str:
    """Replace content between the managed markers, preserving everything else."""
    start_index = existing_readme.find(MARKER_START)
    end_index = existing_readme.find(MARKER_END)
    if start_index == -1 or end_index == -1:
        if existing_readme.strip():
            return existing_readme.rstrip("\n") + "\n\n" + dashboard_markdown + "\n"
        return dashboard_markdown + "\n"
    end_index += len(MARKER_END)
    return existing_readme[:start_index] + dashboard_markdown + existing_readme[end_index:]
```

Delete the plotly import block, the `_ROLLING_WINDOW_DAYS`/`_DEFAULT_*_CHART_PATH` constants, the old multi-chart `render_dashboard_markdown` body, and the entire `render_dashboard` function. Remove the `aggregate`/`timedelta`/`date` imports if now unused (verify with a grep in this file).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/render/test_markdown.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent_usage/render/markdown.py tests/render/test_markdown.py
git commit -m "feat(render): screenshot-only managed README section"
```

---

### Task 4: Delete Plotly renderer and its tests

**Files:**
- Delete: `src/agent_usage/render/plotly.py`
- Delete: `tests/render/test_plotly.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (removal). Precondition: no module imports `render.plotly` (Task 3 removed the last import).

- [ ] **Step 1: Confirm no remaining importers**

Run:
```bash
grep -rn "render.plotly\|render import plotly\|from agent_usage.render.plotly" src scripts tests
```
Expected: no matches. If any appear, fix that caller first (it should already be handled by Tasks 3/5/6).

- [ ] **Step 2: Delete the files**

Run:
```bash
git rm src/agent_usage/render/plotly.py tests/render/test_plotly.py
```

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (no collection errors from the removed module).

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(render): remove plotly chart renderer"
```

---

### Task 5: Rewire local `render` command to screenshot export

**Files:**
- Modify: `src/agent_usage/commands/render.py`
- Modify: `src/agent_usage/cli.py:98-125` (the `render` command)
- Test: `tests/render/test_render_command.py` (create if absent; otherwise modify the existing render-command test)

**Interfaces:**
- Consumes: `dashboard.export.export_dashboard_png`, `render.markdown.render_dashboard_markdown` + `update_readme`.
- Produces: `render(*, ledger_path, output_dir, privacy_policy, today, generated_at, ui_dir, tmp_stage_dir, pie_top_n=6, force_build=False) -> RenderResult` where `RenderResult` keeps `(device_id, readme_path, changed)`.

- [ ] **Step 1: Write the failing test (export mocked, no browser)**

Create `tests/render/test_render_command.py`:

```python
from datetime import date
from pathlib import Path

from agent_usage.commands import render as render_command


def test_render_writes_screenshot_and_readme(tmp_path, monkeypatch):
    calls = {"export": 0}

    def fake_export(output_path, **kwargs):
        calls["export"] += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    monkeypatch.setattr(render_command, "export_dashboard_png", fake_export)

    out = tmp_path / "preview"
    ledger = tmp_path / "ledger.sqlite3"
    result = render_command.render(
        ledger_path=ledger,
        output_dir=out,
        today=date(2026, 7, 24),
        generated_at="2026-07-24 00:00 UTC",
        ui_dir=Path("dashboard-ui"),
        tmp_stage_dir=tmp_path / "stage",
    )

    assert calls["export"] == 1
    assert (out / "assets" / "agent-usage" / "dashboard.png").is_file()
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "assets/agent-usage/dashboard.png" in readme
    assert result.changed is True


def test_render_idempotent_second_run(tmp_path, monkeypatch):
    def fake_export(output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    monkeypatch.setattr(render_command, "export_dashboard_png", fake_export)

    out = tmp_path / "preview"
    kwargs = dict(
        ledger_path=tmp_path / "ledger.sqlite3",
        output_dir=out,
        today=date(2026, 7, 24),
        generated_at="2026-07-24 00:00 UTC",
        ui_dir=Path("dashboard-ui"),
        tmp_stage_dir=tmp_path / "stage",
    )
    render_command.render(**kwargs)
    second = render_command.render(**kwargs)
    assert second.changed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/render/test_render_command.py -v`
Expected: FAIL (old `render` signature; `export_dashboard_png` attribute missing).

- [ ] **Step 3: Rewrite `commands/render.py`**

```python
"""Render a local preview of the profile README dashboard from this device's own ledger data.

Captures this device's interactive dashboard as a single PNG screenshot and
writes the managed README section that embeds it. Entirely local — never
touches Git or the network. Cross-device aggregation only happens once records
are published and picked up by the profile repository's own GitHub Action
(see ``templates/github-workflow.yml``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from agent_usage.dashboard.export import export_dashboard_png
from agent_usage.ledger.repository import LedgerRepository
from agent_usage.privacy import PrivacyPolicy
from agent_usage.render.markdown import (
    DASHBOARD_IMAGE_PATH,
    render_dashboard_markdown,
    update_readme,
)


def _write_if_changed(path: Path, content: str | bytes) -> bool:
    if path.exists() and (
        path.read_bytes() if isinstance(content, bytes) else path.read_text(encoding="utf-8")
    ) == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return True


@dataclass(frozen=True, slots=True)
class RenderResult:
    device_id: str
    readme_path: Path
    changed: bool


def render(
    *,
    ledger_path: Path,
    output_dir: Path,
    ui_dir: Path,
    tmp_stage_dir: Path,
    privacy_policy: PrivacyPolicy = PrivacyPolicy(),
    today: date,
    generated_at: str,
    pie_top_n: int = 6,
    force_build: bool = False,
) -> RenderResult:
    """Regenerate this device's local dashboard preview. Returns whether anything changed."""
    repository = LedgerRepository.open(ledger_path)
    try:
        device_id = repository.get_or_create_device_id()
    finally:
        repository.close()

    screenshot_path = output_dir / DASHBOARD_IMAGE_PATH
    tmp_png = screenshot_path.parent / ".dashboard.png.tmp"
    tmp_png.parent.mkdir(parents=True, exist_ok=True)
    export_dashboard_png(
        tmp_png,
        ledger_path=ledger_path,
        all_devices=False,
        repo_target=None,
        privacy_policy=privacy_policy,
        today=today,
        ui_dir=ui_dir,
        tmp_stage_dir=tmp_stage_dir,
        pie_top_n=pie_top_n,
        force_build=force_build,
    )
    png_bytes = tmp_png.read_bytes()
    tmp_png.unlink(missing_ok=True)
    changed = _write_if_changed(screenshot_path, png_bytes)

    readme_path = output_dir / "README.md"
    existing_readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    updated_readme = update_readme(existing_readme, render_dashboard_markdown())
    changed = _write_if_changed(readme_path, updated_readme) or changed

    return RenderResult(device_id=device_id, readme_path=readme_path, changed=changed)
```

Note: `generated_at` is retained in the signature for CLI compatibility even though the minimal section does not embed it.

- [ ] **Step 4: Update the CLI `render` command**

In `src/agent_usage/cli.py`, update the `render` command body to pass `ui_dir` and a temp stage dir. Ensure `tempfile` and `dashboard_command` are imported (they already are for `dashboard`). Replace the `render` command body:

```python
@app.command()
def render(
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Where to write the local dashboard preview."
    ),
    pie_top_n: int = typer.Option(
        6,
        "--pie-top-n",
        help="Max Skills/MCP slices to show before bucketing the rest into 'Other'.",
    ),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Force a fresh UI build even if the cached build looks current."
    ),
) -> None:
    """Render a local preview of the dashboard from this device's own collected data."""
    if pie_top_n < 1:
        raise typer.BadParameter("--pie-top-n must be at least 1")
    now = datetime.now(timezone.utc)
    config = load_config(config_file_path())
    resolved_output_dir = output_dir or (ledger_file_path().parent / "preview")
    with tempfile.TemporaryDirectory(prefix="agent-usage-render-") as tmp:
        result = render_command.render(
            ledger_path=ledger_file_path(),
            output_dir=resolved_output_dir,
            ui_dir=dashboard_command.UI_DIR,
            tmp_stage_dir=Path(tmp),
            privacy_policy=PrivacyPolicy.from_config(config),
            today=now.date(),
            generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
            pie_top_n=pie_top_n,
            force_build=rebuild,
        )
    typer.echo(f"agent-usage: preview written to {result.readme_path}")
    typer.echo(
        "agent-usage: dashboard changed" if result.changed else "agent-usage: dashboard unchanged"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/render/test_render_command.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Smoke-check the CLI wiring imports**

Run: `uv run python -c "from agent_usage import cli; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add src/agent_usage/commands/render.py src/agent_usage/cli.py tests/render/test_render_command.py
git commit -m "feat(render): produce dashboard screenshot in render command"
```

---

### Task 6: Switch CI script + workflow to screenshot

**Files:**
- Modify: `scripts/build_profile_dashboard.py`
- Modify: `templates/github-workflow.yml`
- Test: `tests/scripts/test_build_profile_dashboard.py` (create if absent)

**Interfaces:**
- Consumes: `dashboard.export.screenshot_payload`, `dashboard.ui_build.ensure_build`, `render.dashboard_data.build_dashboard_data`, `aggregate.validate_and_partition`, `render.markdown.render_dashboard_markdown` + `update_readme`. Keeps the script's existing `_load_entries` (local `data/v1/devices` reader).
- Produces: `build(*, data_dir: Path, readme_path: Path, dashboard_png_path: Path, ui_dir: Path, today: date, generated_at: str, pie_top_n: int = 6) -> bool` and a `--dashboard-png` / `--ui-dir` CLI.
- **Rationale:** CI data is already local at `data/v1/devices`; `build_payload(all_devices=True)` would re-clone the repo over the network (`fetch_device_entries`). So CI reads locally via `_load_entries`, builds the payload with `build_dashboard_data`, and screenshots via `screenshot_payload`.

- [ ] **Step 1: Write the failing test (export mocked)**

Create `tests/scripts/test_build_profile_dashboard.py`:

```python
import sys
from datetime import date
from pathlib import Path

import scripts.build_profile_dashboard as bpd


def test_build_writes_readme_and_png(tmp_path, monkeypatch):
    def fake_screenshot(payload, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    # Screenshot + UI build are the browser/node-dependent parts — stub both.
    monkeypatch.setattr(bpd, "screenshot_payload", fake_screenshot)
    monkeypatch.setattr(bpd, "ensure_build", lambda ui_dir, force=False: ui_dir)

    readme = tmp_path / "README.md"
    png = tmp_path / "assets" / "agent-usage" / "dashboard.png"
    changed = bpd.build(
        data_dir=tmp_path / "data" / "v1" / "devices",
        readme_path=readme,
        dashboard_png_path=png,
        ui_dir=tmp_path / "dashboard-ui",
        today=date(2026, 7, 24),
        generated_at="2026-07-24 00:00 UTC",
    )

    assert changed is True
    assert png.is_file()
    assert "assets/agent-usage/dashboard.png" in readme.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scripts/test_build_profile_dashboard.py -v`
Expected: FAIL (old `build` signature; `screenshot_payload` not imported in the script).

- [ ] **Step 3: Rewrite `scripts/build_profile_dashboard.py`**

Keep the existing `_load_entries` (local `data/v1/devices` reader) and the invalid-record diagnostics loop. Replace the plotly-based `build`, imports, defaults, and arg parsing:

```python
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from agent_usage.aggregate import validate_and_partition
from agent_usage.dashboard.export import screenshot_payload
from agent_usage.dashboard.ui_build import ensure_build
from agent_usage.render.dashboard_data import build_dashboard_data
from agent_usage.render.markdown import (
    DASHBOARD_IMAGE_PATH,
    render_dashboard_markdown,
    update_readme,
)

DEFAULT_DATA_DIR = Path("data/v1/devices")
DEFAULT_README = Path("README.md")
DEFAULT_DASHBOARD_PNG = Path(DASHBOARD_IMAGE_PATH)
DEFAULT_UI_DIR = Path(".agent-usage-src/dashboard-ui")


# _load_entries(...) is kept unchanged from the current script.


def _write_if_changed(path: Path, content: str | bytes) -> bool:
    if path.exists() and (
        path.read_bytes() if isinstance(content, bytes) else path.read_text(encoding="utf-8")
    ) == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return True


def _readme_relative_path(path: Path, *, readme_path: Path) -> str:
    try:
        return path.relative_to(readme_path.parent).as_posix()
    except ValueError:
        return path.as_posix()


def build(
    *,
    data_dir: Path,
    readme_path: Path,
    dashboard_png_path: Path,
    ui_dir: Path,
    today: date,
    generated_at: str,
    pie_top_n: int = 6,
) -> bool:
    """Regenerate the README and dashboard screenshot. Returns True if anything changed.

    Reads the cross-device records locally from ``data_dir`` (the profile repo
    checkout already contains them — no network clone), builds the same
    payload the interactive dashboard uses, and screenshots it.
    """
    entries = _load_entries(data_dir)
    partition = validate_and_partition(entries, today=today)
    for issue in partition.issues:
        print(
            f"agent-usage: skipping invalid record "
            f"device={issue.device_id} date={issue.date} reason={issue.reason}",
            file=sys.stderr,
        )
    payload = build_dashboard_data(partition.valid_payloads, today=today, pie_top_n=pie_top_n)

    dist_dir = ensure_build(ui_dir)
    tmp_png = dashboard_png_path.parent / ".dashboard.png.tmp"
    tmp_png.parent.mkdir(parents=True, exist_ok=True)
    screenshot_payload(payload, tmp_png, dist_dir=dist_dir)
    png_bytes = tmp_png.read_bytes()
    tmp_png.unlink(missing_ok=True)
    changed = _write_if_changed(dashboard_png_path, png_bytes)

    image_ref = _readme_relative_path(dashboard_png_path, readme_path=readme_path)
    existing_readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    updated = update_readme(existing_readme, render_dashboard_markdown(image_path=image_ref))
    changed = _write_if_changed(readme_path, updated) or changed
    return changed


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--dashboard-png", type=Path, default=DEFAULT_DASHBOARD_PNG)
    parser.add_argument("--ui-dir", type=Path, default=DEFAULT_UI_DIR)
    parser.add_argument("--pie-top-n", type=int, default=6)
    parser.add_argument("--today", type=date.fromisoformat, default=None)
    parser.add_argument("--generated-at", type=str, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    now = datetime.now(timezone.utc)
    today = args.today or now.date()
    generated_at = args.generated_at or now.strftime("%Y-%m-%d %H:%M UTC")
    changed = build(
        data_dir=args.data_dir,
        readme_path=args.readme,
        dashboard_png_path=args.dashboard_png,
        ui_dir=args.ui_dir,
        today=today,
        generated_at=generated_at,
        pie_top_n=args.pie_top_n,
    )
    print("agent-usage: dashboard changed" if changed else "agent-usage: dashboard unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Verify `build_dashboard_data`'s signature in `render/dashboard_data.py` matches `(valid_payloads, *, today, pie_top_n)` during implementation (it is the same call `build_payload` makes internally).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scripts/test_build_profile_dashboard.py -v`
Expected: PASS.

- [ ] **Step 5: Update the workflow template**

In `templates/github-workflow.yml`, update the header comment (README + `assets/agent-usage/dashboard.png`), and rewrite the build steps after "Check out agent-usage collector":

```yaml
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Enable pnpm
        run: corepack enable

      - name: Install agent-usage
        run: pip install ./.agent-usage-src

      - name: Install Chromium for Playwright
        run: python -m playwright install --with-deps chromium

      - name: Validate public records and render dashboard
        run: |
          python .agent-usage-src/scripts/build_profile_dashboard.py \
            --data-dir data/v1/devices \
            --readme README.md \
            --dashboard-png assets/agent-usage/dashboard.png \
            --ui-dir .agent-usage-src/dashboard-ui

      - name: Commit and push if the dashboard changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add README.md assets/agent-usage/dashboard.png
          if git status --porcelain | grep -q .; then
            git commit -m "chore: update agent usage dashboard"
            git push origin HEAD:${{ github.ref_name }}
          else
            echo "agent-usage: nothing to commit"
          fi
```

(The React dist is built by `ensure_build` inside `export_dashboard_png`, which runs `pnpm install && pnpm build` on demand — hence Node + pnpm are required above.)

- [ ] **Step 6: Run the full suite + lint**

Run:
```bash
uv run pytest -q
uv run ruff check src scripts tests
```
Expected: PASS / no lint errors.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_profile_dashboard.py templates/github-workflow.yml tests/scripts/test_build_profile_dashboard.py
git commit -m "feat(ci): render README dashboard via screenshot"
```

---

### Task 7: Docs + final sweep

**Files:**
- Modify: `README.md` (any mention of Plotly charts / chart assets)
- Modify: `AGENTS.md` and `docs/*.md` if they reference the old chart pipeline

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (docs only).

- [ ] **Step 1: Find stale references**

Run:
```bash
grep -rin "plotly\|kaleido\|token-activity\|agent-share.png\|skills.png\|mcp.png" README.md AGENTS.md docs
```
Expected: a list of references to update.

- [ ] **Step 2: Update prose**

Edit each hit to describe the single screenshot pipeline (`assets/agent-usage/dashboard.png`, Playwright/Chromium) instead of Plotly PNG charts. Keep changes minimal and factual.

- [ ] **Step 3: Verify no code references remain**

Run:
```bash
grep -rin "plotly\|kaleido" src scripts tests pyproject.toml
```
Expected: no matches.

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md docs
git commit -m "docs: describe screenshot-based dashboard pipeline"
```

---

## Self-Review Notes

- **Spec coverage:** export module (Task 2), screenshot-only section (Task 3), plotly deletion (Tasks 1,4), render fold-in (Task 5), CI both script + workflow (Task 6), docs (Task 7). All spec sections mapped.
- **Resolved:** cross-device CI payload source. `fetch_device_entries` (used by `build_payload(all_devices=True)`) git-clones the profile repo over the network — wrong for CI where the data is already local. CI therefore reads locally via `_load_entries` + `build_dashboard_data` and screenshots via `screenshot_payload` (Task 6). The local `render` path keeps the `export_dashboard_png` convenience wrapper (`all_devices=False`).
- **Type consistency:** `screenshot_payload(payload, output_path, *, dist_dir, ...)` used identically in Tasks 2 and 6. `export_dashboard_png(...)` identical across Tasks 2 and 5. `render_dashboard_markdown(image_path=...)` and `DASHBOARD_IMAGE_PATH` consistent across Tasks 3, 5, 6.
