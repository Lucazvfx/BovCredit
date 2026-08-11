from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_fields_stylesheet_defines_domain_tokens():
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")

    for token in (
        "--ork-forest",
        "--ork-moss",
        "--ork-sage",
        "--ork-sand",
        "--ork-oat",
        "--ork-clay",
        "--ork-soil",
        "--ork-ink",
    ):
        assert token in css


def test_shell_has_mobile_and_desktop_navigation():
    sidebar = (
        ROOT / "templates" / "partials" / "fields_sidebar.html"
    ).read_text(encoding="utf-8")
    mobile = (
        ROOT / "templates" / "partials" / "fields_mobile_nav.html"
    ).read_text(encoding="utf-8")

    assert 'aria-label="Navegação principal"' in sidebar
    assert 'aria-label="Navegação móvel"' in mobile
    assert "data-ork-nav" in sidebar
    assert "data-ork-nav" in mobile


def test_shell_controller_exposes_safe_initializer():
    javascript = (ROOT / "static" / "orkavyn-shell.js").read_text(encoding="utf-8")

    assert "window.OrkavynShell" in javascript
    assert "init()" in javascript
    assert "DOMContentLoaded" in javascript


def test_index_shell_preserves_critical_controls():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    for selector in (
        'id="empresa-ativa-select"',
        'id="pdf-inp-main"',
        'id="tab-res"',
        'id="tab-cen"',
        'id="loading-ov"',
    ):
        assert selector in html
    assert "{% include 'partials/fields_sidebar.html' %}" in html
    assert "{% include 'partials/fields_mobile_nav.html' %}" in html
    assert "orkavyn-fields.css" in html
    assert "orkavyn-shell.js" in html


def test_admin_loads_the_shared_fields_surface():
    html = (ROOT / "templates" / "admin.html").read_text(encoding="utf-8")

    assert "orkavyn-fields.css" in html
    assert 'class="ork-shell' in html
