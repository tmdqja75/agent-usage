from datetime import date

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
