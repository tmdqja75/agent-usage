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
