"""Contrato do dashboard repaginado (skill orkavyn-ui): tokens, formulário do
ciclo/estresse, payload tipado e parecer em abas sem innerHTML com dado externo.

São checagens estáticas sobre template/CSS/JS (não há navegador na suíte); o
comportamento no navegador foi conferido à parte com Playwright.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "orkavyn-dashboard.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "orkavyn-dashboard.js").read_text(encoding="utf-8")
SKILL = (ROOT / ".claude" / "skills" / "orkavyn-ui" / "SKILL.md").read_text(encoding="utf-8")

TOKENS = (
    "brand-primary", "brand-primary-hover", "brand-hero-start", "brand-hero-end",
    "brand-tint", "bg-canvas", "bg-surface", "bg-subtle", "border-subtle",
    "border-strong", "text-primary", "text-secondary", "text-muted",
    "text-on-brand", "status-approve-fg", "status-approve-bg", "status-warn-fg",
    "status-warn-bg", "status-reject-fg", "status-reject-bg",
)


def _bloco(css: str, abre: str) -> str:
    ini = css.index(abre)
    return css[ini:css.index("}", ini)]


def test_tokens_definidos_em_light_e_dark_e_documentados_na_skill():
    light = _bloco(CSS, ":root {")
    dark = _bloco(CSS, '[data-theme="dark"] {')
    for t in TOKENS:
        assert f"--{t}:" in light, f"{t} ausente no light"
        assert f"--{t}:" in dark, f"{t} ausente no dark"
        assert f"`--{t}`" in SKILL, f"{t} ausente na skill"
    assert "--brand-primary: #166534" in light and "--brand-primary: #22C55E" in dark


def test_index_carrega_assets_e_tema_sem_flash():
    assert "orkavyn-dashboard.css" in INDEX and "orkavyn-dashboard.js" in INDEX
    # O tema é aplicado no <head>, antes do CSS, para não piscar claro->escuro.
    assert INDEX.index('"orkavyn_theme"') < INDEX.index("orkavyn-fields.css")
    assert "family=Inter" in INDEX


def test_formulario_em_tres_blocos_com_quatro_cards_de_sistema():
    for titulo in ("1. Operação e Crédito", "2. Sistema Pecuário e Ciclo", "3. Estresse do Boi"):
        assert titulo in INDEX, titulo
    valores = re.findall(r'class="od-sys" data-valor="([a-z_]+)"', INDEX)
    assert valores == ["cria", "recria", "engorda", "ciclo_completo"]
    for campo in ("capital_giro_inicial", "preco_arroba_base",
                  "custo_reposicao_anual", "custo_suplementacao_anual",
                  "frequencia_pagamento"):
        assert f'id="{campo}"' in INDEX, campo
    # O select continua existindo (escondido): rascunho e demais leitores dele.
    assert re.search(r'<select id="sistema_produtivo" hidden', INDEX)
    assert "juntos" in INDEX  # aviso do trio do estresse


def test_payload_usa_helper_tipado_e_barra_antes_do_loading():
    assert "OrkavynDash.lerCamposNovos()" in INDEX
    assert "Object.assign(body,_novos.campos)" in INDEX
    assert INDEX.index("OrkavynDash.lerCamposNovos()") < INDEX.index("showLoading(['Analisando composição")
    # As leituras antigas, sem tipagem, saíram.
    assert "document.getElementById('sistema_produtivo').value;" not in INDEX


def test_helper_converte_com_number_e_omite_vazios():
    corpo = JS[JS.index("function lerCamposNovos"):JS.index("// ── parecer: hero")]
    assert corpo.count("Number(") >= 2
    assert 'giroRaw !== ""' in corpo and "preenchidos.length < brutos.length" in corpo
    assert "Number.isFinite" in corpo
    # Preço da arroba é > 0 (o servidor deriva o volume dele).
    assert 'b.id === "preco_arroba_base" ? n > 0' in corpo


def test_js_novo_nao_usa_innerhtml_nem_apis_equivalentes():
    # Comentários podem citar a regra; o código não.
    codigo = re.sub(r"/\*.*?\*/|//[^\n]*", "", JS, flags=re.S)
    for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert proibido not in codigo, proibido


def test_parecer_tem_hero_banner_e_tres_abas():
    for trecho in ("Resumo / Base", "Ciclo 12m", "Estresse do Boi",
                   "quebra_caixa_com_dscr_ok === true", "em_ruptura === true",
                   "Ponto de ruptura (@)", "Vale de caixa (12m)", "Rating",
                   "DSCR mínimo", "Crédito máximo", "Brasil Central"):
        assert trecho in JS, trecho
    for cenario in ("queda_arroba", "alta_reposicao", "alta_suplementacao",
                    "seca_severa", "tesoura_margem_moderada", "tesoura_margem_severa"):
        assert cenario in JS, cenario
    assert "linear-gradient(135deg, var(--brand-hero-start), var(--brand-hero-end))" in CSS
    assert "OrkavynDash.renderParecer(data)" in INDEX


def test_ciclo_legado_migrou_para_a_aba_sem_funcao_orfa():
    assert "renderCicloPecuario" not in INDEX


def test_numeros_com_tabular_nums_e_tabela_alinhada_a_direita():
    assert "tabular-nums" in CSS
    assert ".od-table th:not(:first-child)" in CSS and "text-align: right" in CSS


def test_resumo_legado_nao_repete_numeros_do_hero_e_dscr_usa_virgula():
    ini = INDEX.index("function renderDecisionSummary")
    corpo = INDEX[ini:INDEX.index("function renderResult", ini)]
    for repetido in ("Capacidade estimada", "DSCR mínimo", "<span>Risco</span>"):
        assert repetido not in corpo, repetido
    for mantido in ("Resultado operacional", "Sistema identificado", "Análise preliminar"):
        assert mantido in corpo, mantido
    # Nenhum DSCR formatado com ponto decimal ou sufixo "x".
    assert "toFixed(2)+'x'" not in INDEX
    assert "_prNum(c.dscr_minimo, 2)}x" not in INDEX
    assert "const fDscr=" in INDEX


def test_mobile_header_em_fluxo_normal_e_nav_fixa_no_fundo():
    assert re.search(r"\.ork-context-header \{ height: auto;", CSS)
    nav = CSS[CSS.index(".ork-dashboard-surface .ork-mobile-nav {\n    right"):]
    nav = nav[:nav.index("}")]
    assert "bottom: 0" in nav and "env(safe-area-inset-bottom)" in nav
    assert "env(safe-area-inset-bottom)" in CSS[CSS.index(".ork-main { padding-bottom"):][:120]
