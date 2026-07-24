# Dashboard Screenshot README — Design

**Date:** 2026-07-24
**Status:** Approved (design), pending implementation plan

## Problem

The profile README dashboard is currently built from five static Plotly
PNG charts (`render/plotly.py` + Kaleido). This duplicates the visual
language of the interactive React dashboard (`dashboard-ui/`) in a second,
lower-fidelity rendering path that must be maintained in parallel. We want a
single source of visual truth: capture the real React dashboard as one
screenshot and embed that in the README.

## Goal

Remove Plotly entirely. Replace the managed README section's five charts and
markdown tables with a single full-page screenshot of the React dashboard,
produced with a headless Playwright/Chromium browser. Apply to both render
paths:

- **Local** — `agent-usage render` (this device only, into
  `agent-usage-preview/`).
- **CI** — `scripts/build_profile_dashboard.py`, run by the profile
  repository's GitHub Action (`templates/github-workflow.yml`), cross-device,
  producing the public README.

## Decisions (locked)

- **README managed section = screenshot only.** Drop the five chart images
  *and* the markdown tables/numbers. Section becomes a single image reference
  plus the generated-at line.
- **CI switches too.** The profile-repo Action builds the React dist and runs
  Playwright/Chromium on `ubuntu-latest` to screenshot the aggregated
  cross-device dashboard.
- **Folded into `render`.** No new subcommand; `render` reuses the payload +
  server + screenshot path in place of Plotly chart writes.
- **React dist built on the fly in CI** via Node + pnpm (`ensure_build`).
  `dist/` stays gitignored; no committed build artifact.
- **Auto-install Chromium** on first local render if the browser binary is
  missing: attempt launch → on missing-browser error, run
  `playwright install chromium`, retry once.

## Architecture

### New module: `src/agent_usage/dashboard/export.py`

Single entry point:

```python
def export_dashboard_png(
    output_path: Path,
    *,
    ledger_path: Path,
    all_devices: bool,
    privacy_policy: PrivacyPolicy,
    today: date,
    ui_dir: Path,
    lang: str = "en",
    width: int = 1100,
    scale: int = 2,
    tmp_stage_dir: Path,
) -> None:
```

Flow:

1. `payload = build_payload(...)` — reuse existing
   `dashboard/payload.py:build_payload` (same data.json as the interactive
   dashboard; honors `all_devices` and privacy policy).
2. `dist_dir = ensure_build(ui_dir)` — reuse `dashboard/ui_build.py`.
3. `server = make_server(payload, dist_dir=dist_dir, host="127.0.0.1",
   port=0, lang=lang)` — reuse `dashboard/server.py:make_server`. Bind an
   OS-selected ephemeral port. Run `serve_forever()` on a daemon thread; read
   the actual port from `server.server_address[1]`.
4. Launch Playwright Chromium (sync API), headless.
   - Context: `viewport={"width": width, "height": 900}`,
     `device_scale_factor=scale`, `color_scheme="dark"`,
     `reduced_motion="reduce"`.
   - `context.route("**/*", handler)` — allow only URLs starting with
     `http://127.0.0.1:{port}/`; abort everything else (defense in depth: the
     export page loads local resources only).
5. Navigate + wait until rendered:
   - `page.goto(url, wait_until="networkidle")`
   - `page.wait_for_function("document.querySelector('.dashboard') && "
     "!document.body.innerText.includes('Loading…')")`
   - `page.evaluate("document.fonts.ready")`
   - `page.wait_for_timeout(2000)` — fixed 2s settle for any residual chart
     animation after reduced-motion.
6. `page.screenshot(path=output_path, full_page=True)`.
7. `finally:` shut the server down and close it (never leave it running);
   close the browser/context.

**Missing-browser handling.** Wrap the launch. On the Playwright error that
indicates the Chromium binary is not installed, run
`python -m playwright install chromium` (subprocess) once, then retry the
launch. If it still fails, raise a clear user-facing error.

### `commands/render.py` rewrite

- Managed section becomes screenshot-only. Write one asset:
  `assets/agent-usage/dashboard.png`.
- Replace the five `render_dashboard(...)` chart writes with a single
  `export_dashboard_png(output_path=<preview>/assets/agent-usage/dashboard.png,
  ledger_path=..., all_devices=False, privacy_policy=..., today=..., ui_dir=...,
  tmp_stage_dir=...)`.
- README body: `update_readme(existing, dashboard_markdown)` where
  `dashboard_markdown` now renders the screenshot section (see below).
- `RenderResult` unchanged (`device_id`, `readme_path`, `changed`). Preserve
  the write-if-changed behavior for both README and the PNG.
- `render` gains access to `ui_dir` (same resolution as
  `commands/dashboard.py`: repo-root `dashboard-ui/`) and a `tmp_stage_dir`.

### `render/markdown.py` simplification

- `render_dashboard_markdown` collapses to a single-image section between the
  existing `MARKER_START` / `MARKER_END`:

  ```markdown
  <!-- agent-usage:start -->
  ## Agent Usage

  ![Agent Usage dashboard](assets/agent-usage/dashboard.png)

  <!-- agent-usage:end -->
  ```

  (Exact heading/alt text finalized in the plan.) Keep `update_readme`
  unchanged — marker replace/append + idempotence still hold.
- Remove the five chart-path parameters and all table/aggregation code that
  existed solely to feed Plotly. Delete the `render/plotly` import.
- `render_dashboard` (the function that returned `{"markdown", "charts"}`) is
  removed or reduced: chart bytes no longer exist; the screenshot is produced
  by `export.py`, not here. Callers updated accordingly.

### Delete Plotly

- Delete `src/agent_usage/render/plotly.py`.
- Delete `tests/render/test_plotly.py`.
- `pyproject.toml`: remove `plotly` and `kaleido`; add `playwright`.
- Remove now-dead helpers in `render/_counters.py` only if nothing else uses
  them (verify with grep during implementation; do not remove shared code).

### CI: `scripts/build_profile_dashboard.py` + workflow

**Script** (`build_profile_dashboard.py`):

- Replace the plotly chart CLI flags
  (`--rolling-chart/--total-chart/--skills-chart/--mcp-chart`) with a single
  `--dashboard-png assets/agent-usage/dashboard.png`.
- Assemble the cross-device payload (same aggregation the Action already
  performs from `data/v1/devices`) and call `export_dashboard_png(...)` with
  `all_devices=True` semantics and `ui_dir` pointing at the checked-out
  collector repo's `dashboard-ui/`.
- Still write the README managed section (screenshot-only markdown).

**Workflow** (`templates/github-workflow.yml`):

- Add `actions/setup-node` + enable pnpm (corepack or `pnpm/action-setup`).
- Build the React dist (via `ensure_build`, invoked inside the script, or an
  explicit `pnpm install && pnpm build` step in `.agent-usage-src/dashboard-ui`).
- After `pip install ./.agent-usage-src`: `python -m playwright install
  --with-deps chromium`.
- Update the render step to pass `--dashboard-png ...`.
- Update `git add` to `README.md assets/agent-usage/dashboard.png` (single
  asset); drop stale chart paths.
- Keep existing concurrency/permissions/trigger scope.

## Data flow

```
ledger / data/v1/devices
        │
        ▼
 build_payload  ──►  data.json (in memory)
        │
        ▼
 make_server (127.0.0.1:0)  ◄── ensure_build → dist/ (React)
        │
        ▼
 Playwright Chromium (headless, dark, reduced-motion, 2s settle)
        │
        ▼
 full_page screenshot ──► assets/agent-usage/dashboard.png
        │
        ▼
 update_readme (screenshot-only managed section) ──► README.md
```

## Error handling

- **UI not built / Node missing** — `ensure_build` already raises
  `UIBuildError`; surface as a clean render/CLI message.
- **Chromium missing (local)** — auto-install once, then retry; final failure
  raises a clear "run `playwright install chromium`" message.
- **Server lifecycle** — always shut down in `finally`; ephemeral port avoids
  collisions.
- **Route allow-list** — non-loopback requests aborted, so a broken asset
  reference cannot reach the network during export.

## Testing

- `export.py`: test payload→server→screenshot with a real ephemeral server
  and headless Chromium producing a non-empty PNG (integration test, gated so
  it skips cleanly when Chromium is unavailable). Unit-test the route
  allow-list predicate and the missing-browser retry logic (mock the
  subprocess + launch).
- `markdown.py`: assert the managed section contains the single image
  reference and preserves surrounding README content; idempotence unchanged.
- `render.py`: assert one PNG asset written, README updated, `changed`
  semantics correct on repeat runs (mock `export_dashboard_png` to avoid a
  browser in unit tests).
- Remove `test_plotly.py`. Update `test_markdown.py` for the screenshot-only
  section.

## Out of scope

- Redesigning the React dashboard visuals.
- Changing the interactive `dashboard` command behavior.
- Light-mode screenshot variants / multiple themes.
- Publishing tagged releases of the collector for the Action to pin.

## Risks

- **CI weight** — Node build + `playwright install --with-deps chromium` adds
  time and apt deps on the runner. Acceptable; single serialized job.
- **Animation timing** — fixed 2s settle assumed sufficient after
  reduced-motion. If a chart animates longer, bump the timeout; do not switch
  to unbounded waits.
- **Font readiness** — `document.fonts.ready` awaited before capture to avoid
  FOUT in the screenshot.
