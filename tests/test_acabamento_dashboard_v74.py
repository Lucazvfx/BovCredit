"""Acabamento do dashboard: topbar mobile, rodapé no dark e cache-busting."""
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "orkavyn-dashboard.css").read_text(encoding="utf-8")


def test_assets_do_dashboard_tem_versao_na_query():
    for arq in ("orkavyn-dashboard.css", "orkavyn-dashboard.js"):
        assert re.search(rf"filename='{re.escape(arq)}'\) }}}}\?v=\d+\"", INDEX), arq


def test_vaca_some_ate_480px_com_especificidade_que_vence_o_display_base():
    # A regra base usa o seletor com #hdr-vaca; a do celular precisa do mesmo,
    # senão o inline-flex base ganha do display:none do index.html.
    seletor = ".ork-dashboard-surface .od-topbar #hdr-vaca"
    base = CSS.index(seletor + " { display: inline-flex; }")
    oculta = CSS.index(seletor + " { display: none; }")
    assert oculta > base
    assert CSS.rfind("@media (max-width: 480px)", 0, oculta) > base


def test_rodape_usa_tokens_e_nao_cor_fixa():
    rodape = INDEX[INDEX.index("<footer"):INDEX.index("</footer>")]
    assert 'class="od-footer"' in rodape
    assert "#000" not in rodape and "style=" not in rodape
    bloco = CSS[CSS.index(".od-footer {"):]
    assert "var(--text-secondary)" in bloco and "var(--text-primary)" in bloco
