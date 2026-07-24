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
