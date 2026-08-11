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


def test_result_renderer_keeps_decision_contract_and_evidence_targets():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    for key in (
        "parecer",
        "qualidade_dados",
        "fluxo_mensal",
        "comparacao_cenarios",
        "explicacao_classificacao",
    ):
        assert key in html
    for panel in (
        "panel-resultado",
        "panel-cenarios",
        "panel-historico",
        "panel-ajuda",
    ):
        assert f'id="{panel}"' in html
    assert "ork-decision-summary" in html
    for target in ("ev-quality", "ev-assumptions", "ev-sources", "ev-limitations"):
        assert f'id="{target}"' in html


def test_auth_and_legal_templates_load_fields_stylesheet():
    for name in (
        "login.html",
        "login_2fa.html",
        "register.html",
        "cadastro.html",
        "esqueci_senha.html",
        "redefinir_senha.html",
        "termos.html",
        "privacidade.html",
    ):
        html = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "orkavyn-fields.css" in html, name


def test_login_preserves_field_names_and_uses_auth_layout():
    html = (ROOT / "templates" / "login.html").read_text(encoding="utf-8")

    assert 'name="email"' in html
    assert 'name="senha"' in html
    assert 'class="ork-auth-layout' in html


def test_landing_keeps_real_routes_and_avoids_unverified_telemetry():
    html = (ROOT / "templates" / "landing.html").read_text(encoding="utf-8")

    assert "url_for('login')" in html
    assert "Orkavyn Agro Intelligence" in html
    assert "orkavyn-fields.css" in html
    assert "99,8%" not in html
    assert "< 4min" not in html
    assert "BovCredit" not in html


def test_admin_keeps_operational_access_controls():
    html = (ROOT / "templates" / "admin.html").read_text(encoding="utf-8")

    for marker in ("empresas", "auditoria", "LGPD"):
        assert marker.lower() in html.lower()
    assert "admin_criar_empresa" in html
    assert "admin_vincular_empresa" in html


def test_motion_and_focus_contracts_exist():
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_loading_overlay_is_announced_only_while_active():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'id="loading-ov"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-hidden="true"' in html
    assert 'aria-busy="false"' in html
    assert "overlay.setAttribute('aria-hidden','false')" in html
    assert "overlay.setAttribute('aria-busy','true')" in html
    assert "overlay.setAttribute('aria-hidden','true')" in html
    assert "overlay.setAttribute('aria-busy','false')" in html
