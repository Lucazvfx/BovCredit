import re
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _css_rule(source: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", source, re.S)
    assert match, f"regra ausente: {selector}"
    return match.group(1)


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


def test_light_sidebar_preserves_destinations_and_moves_account_to_footer():
    sidebar = (
        ROOT / "templates" / "partials" / "fields_sidebar.html"
    ).read_text(encoding="utf-8")
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "Análise econômico-produtiva" in sidebar
    for destination in ("entrada", "resultado", "cenarios", "historico", "ajuda"):
        assert f'data-ork-nav="{destination}"' in sidebar
        assert f"showTab('{destination}', this)" in sidebar
    assert sidebar.count("<svg") == 5
    assert 'class="ork-sidebar__account"' in sidebar
    assert "usuario.nome" in sidebar
    assert "usuario.email" in sidebar
    assert 'href="/logout"' in sidebar
    assert 'onclick="logout()"' not in html


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


def test_dashboard_uses_static_ambient_herd_background():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")

    assert 'class="ork-surface ork-dashboard-surface"' in html
    assert 'id="bg-rebanho"' in html
    assert "document.addEventListener('mousemove'" not in html
    assert "maskImage = mask" not in html

    background = _css_rule(css, ".ork-dashboard-surface #bg-rebanho")
    assert "rebanho-bg.jpg" in background
    assert re.search(r"opacity:\s*0\.1[0-5]", background)


def test_dashboard_hover_does_not_move_controls_or_cards():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")
    dashboard_sources = html + "\n" + css

    for selector in (".ork-action:hover", ".btn-p:hover", ".sc-card:hover"):
        rule = _css_rule(dashboard_sources, selector)
        assert "translate" not in rule
        assert "scale(" not in rule


def test_dashboard_uses_forest_text_and_readable_translucent_surfaces():
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")

    surface = _css_rule(css, ".ork-dashboard-surface")
    panels = _css_rule(css, ".ork-dashboard-surface .ork-result-view .card")
    headings = _css_rule(css, ".ork-dashboard-surface .ork-result-view .ct")

    assert "var(--ork-sand)" in surface
    assert "rgba(251, 247, 239" in panels
    assert "var(--ork-forest)" in headings
