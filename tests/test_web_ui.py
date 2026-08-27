from pathlib import Path


WEB = Path("src/hierarchy_account_transfer/web")


def test_ui_contains_complete_user_flow():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "app.js").read_text(encoding="utf-8")
    for element_id in (
        "upload-form",
        "analysis-form",
        "account-list",
        "metrics",
        "control-download",
        "export-button",
        "blocker-rows",
    ):
        assert f'id="{element_id}"' in html
    for endpoint in (
        "/api/v1/inspect",
        "/api/v1/runs/analyze",
        "/pair-candidates",
        "/export",
    ):
        assert endpoint in script


def test_ui_is_responsive_and_has_no_external_dependencies():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert "@media(max-width:800px)" in css
    assert "@media(max-width:480px)" in css
    assert "http://" not in html + css
    assert "https://" not in html + css
